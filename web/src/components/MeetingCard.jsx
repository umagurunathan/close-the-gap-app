import { useState } from "react";
import { api } from "../api.js";
import { actionLabel, statusLabel, urgencyLabel, fmtWhen } from "../format.js";
import { AgentTrail, AiSource, ProxySuggestions, RecommendationDetails, cap, declineNotice } from "./aiBits.jsx";
import { Icon } from "./Icons.jsx";
import Invitees from "./Invitees.jsx";
import ProxyPanel from "./ProxyPanel.jsx";

// One card per (meeting, absent person). Used in Attendee Mode and Past. The organizer sees OrganizerCard instead.
export default function MeetingCard({ item, people, me, role, refresh, quiet = false, readOnly = false, activity = [] }) {
  const [mode, setMode] = useState("idle"); // idle | proxy | confirm
  const [proposal, setProposal] = useState(null);
  const [showActions, setShowActions] = useState(!quiet);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [meetingNotes, setMeetingNotes] = useState([]);
  const [notesLoaded, setNotesLoaded] = useState(false);
  const [notesLoading, setNotesLoading] = useState(false);
  const [notesSaving, setNotesSaving] = useState(false);
  const [meetSaving, setMeetSaving] = useState(false);
  const [meetImporting, setMeetImporting] = useState(false);
  const [meetStatus, setMeetStatus] = useState(null);
  const [meetUrlInput, setMeetUrlInput] = useState("");
  const [meetingNoteText, setMeetingNoteText] = useState("");
  const [noteReaders, setNoteReaders] = useState([]);

  const ev = item.event;
  const name = (id) => people[id]?.name ?? id;
  const inviteeIds = [...new Set(ev.attendees.map((a) => a.personId).filter((id) => id !== ev.organizerId))];
  const canViewMeetingNotes = ev.organizerId === me || inviteeIds.includes(me);
  const iAmOrganizer = ev.organizerId === me;
  const terminal = item.status === "rescheduled" || item.status === "cancelled";
  // Both sides can act: the absent person sees the organizer can too, and vice versa (said on that person's chip).
  const alsoActsId = readOnly || terminal ? null
    : role === "attendee" ? (ev.organizerId !== me ? ev.organizerId : null) : item.absentPersonId;
  const organizerTag = ev.organizerId === item.absentPersonId;
  const ai = item.ai;
  // "me" = the absent person is the one looking; otherwise labels use their first name
  const mine = item.absentPersonId === me;
  const who = name(item.absentPersonId).split(" ")[0];
  const label = (a) => actionLabel(a, mine, who);
  const urgency = urgencyLabel(item.urgency, item.hoursToStart); // amber within 3 days, red within 24 hours

  async function toggleMeetingNotes() {
    setError("");
    if (notesOpen) {
      setNotesOpen(false);
      return;
    }
    setNotesOpen(true);
    if (notesLoaded) return;
    setNotesLoading(true);
    try {
      const [notes, meet] = await Promise.all([
        api(`/items/${item.id}/notes`, { person: me }),
        api(`/items/${item.id}/meet`, { person: me }),
      ]);
      setMeetingNotes(notes);
      setMeetStatus(meet);
      setMeetUrlInput(meet.meetUrl || "");
      setNotesLoaded(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setNotesLoading(false);
    }
  }

  async function saveMeetingNote(e) {
    e.preventDefault();
    setNotesSaving(true);
    setError("");
    try {
      const saved = await api(`/items/${item.id}/notes`, {
        method: "POST",
        person: me,
        body: { text: meetingNoteText, sharedWith: noteReaders },
      });
      setMeetingNotes((current) => [...current, saved]);
      setMeetingNoteText("");
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setNotesSaving(false);
    }
  }

  async function saveMeetLink(e) {
    e.preventDefault();
    setMeetSaving(true);
    setError("");
    try {
      const status = await api(`/items/${item.id}/meet`, {
        method: "PUT",
        person: me,
        body: { meetUrl: meetUrlInput },
      });
      setMeetStatus(status);
      setMeetUrlInput(status.meetUrl || "");
    } catch (err) {
      setError(err.message);
    } finally {
      setMeetSaving(false);
    }
  }

  async function connectGoogleMeet() {
    setError("");
    try {
      const { authorizationUrl } = await api("/integrations/google-meet/authorize", { person: me });
      window.location.assign(authorizationUrl);
    } catch (err) {
      setError(err.message);
    }
  }

  async function importMeetTranscript() {
    setMeetImporting(true);
    setError("");
    try {
      const imported = await api(`/items/${item.id}/meet/import`, {
        method: "POST",
        person: me,
        body: { sharedWith: noteReaders },
      });
      setMeetingNotes((current) => [
        ...current.filter((currentNote) => currentNote.docId !== imported.docId),
        imported,
      ]);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setMeetImporting(false);
    }
  }

  async function act(action, proxyId, extra = {}) {
    setBusy(true);
    setError("");
    try {
      await api(`/items/${item.id}/action`, {
        method: "POST",
        person: me,
        body: { action, proxyId, ...extra },
      });
      setMode("idle");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function onReschedule() {
    if (!iAmOrganizer) return act("reschedule"); // becomes a task for the organizer
    setError("");
    try {
      setProposal(await api(`/items/${item.id}/proposed-time`, { person: me }));
      setMode("confirm");
    } catch (e) {
      setError(e.message);
    }
  }

  // The recommended action comes first and stands out; the others follow in the usual order.
  const firstName = (id) => name(id).split(" ")[0];
  // After a proxy declined, it is the person's call again: a general "Choose another proxy", no star, all buttons equal.
  const declined = item.declinedProxyIds || [];
  const afterDecline = item.status === "proxy_declined" && declined.length > 0;
  const buttons = [
    mine && item.ownerRole === "leaver" && { action: "attend", text: label("attend"), onClick: () => act("attend") },
    { action: "proceed_without", text: label("proceed_without"), onClick: () => act("proceed_without") },
    {
      action: "proxy",
      text: afterDecline ? "Choose another proxy"
        : ai.recommendation === "proxy" && ai.suggestedProxyId ? `Ask ${firstName(ai.suggestedProxyId)} to cover` : "Choose a proxy",
      onClick: () => setMode("proxy"),
    },
    { action: "reschedule", text: iAmOrganizer ? "Reschedule" : "Ask to reschedule", onClick: onReschedule,
      hint: iAmOrganizer ? undefined : `Asks ${name(ev.organizerId)} (organizer) to reschedule` },
    { action: "cancel", text: iAmOrganizer ? "Cancel this meeting" : "Ask to cancel", onClick: () => act("cancel"), danger: true,
      hint: iAmOrganizer ? undefined : `Asks ${name(ev.organizerId)} (organizer) to cancel` },
  ].filter(Boolean);
  // Only point at the recommendation while a decision is still needed (not after someone already acted on it).
  const deciding = ["pending_decision", "proxy_declined", "no_slot_found"].includes(item.status);
  const highlight = deciding && !afterDecline ? ai.recommendation : null;
  // Once someone has acted, that action comes first in green with a tick and says what happened; the rest stay
  // available after "or change to:", because people may change their mind.
  const taken = !deciding && item.chosenAction ? item.chosenAction : null;
  const proxyFirst = item.chosenProxyId ? firstName(item.chosenProxyId) : "";
  const takenText = {
    proxy: item.status === "proxy_accepted" ? `${proxyFirst} will cover` : `${proxyFirst} asked to cover`,
    proceed_without: mine ? "Going on without you" : `Going on without ${who}`,
    attend: "You'll attend",
    reschedule: "Organizer asked to reschedule",
    cancel: "Organizer asked to cancel",
  };
  const first = taken ?? highlight;
  const ordered = [...buttons.filter((b) => b.action === first), ...buttons.filter((b) => b.action !== first)];
  const leads = Boolean(first) && ordered[0]?.action === first;   // one button leads; the rest are smaller
  const attention = item.urgency || (item.needsAttention ? "open" : "settled");

  return (
    <article className={`card kind-${item.kind} attn-${attention}`}>
      <header className="card-head">
        <div>
          <h3>{ev.title}</h3>
          <div className="when"><Icon name="calendar" size={14} />{fmtWhen(ev.start)}</div>
        </div>
        <div className="chips">
          {organizerTag && <span className="chip chip-tag">Organizer</span>}
          {urgency && <span className={`chip urgency-${item.urgency}`}>{urgency}</span>}
          <span className={`chip status-${item.status}`}>{statusLabel(item.status, mine, who, item.chosenAction)}</span>
        </div>
      </header>

      <Invitees event={ev} absentId={item.absentPersonId} people={people} alsoActsId={alsoActsId} />

      {canViewMeetingNotes && <section className="meeting-notes">
        <button className="link" aria-expanded={notesOpen} onClick={toggleMeetingNotes}>
          {notesOpen ? "Hide meeting notes" : "Meeting notes"}
        </button>
        {notesOpen && (
          <div className="panel">
            <h4>Meeting notes</h4>
            {notesLoading ? <p className="reason">Loading notes…</p> : meetingNotes.length === 0 ? (
              <p className="reason">No notes are shared with you yet.</p>
            ) : meetingNotes.map((meetingNote) => (
              <div className="meeting-note" key={meetingNote.docId}>
                <div className="reason">
                  {meetingNote.source === "google_meet_transcript" ? "Google Meet transcript · " : ""}
                  {fmtWhen(meetingNote.modifiedAt)}
                </div>
                <p className="note-text">{meetingNote.text}</p>
                {iAmOrganizer && (
                  <div className="reason">
                    Shared with: {meetingNote.sharedWith.map(name).join(", ") || "organizer only"}
                  </div>
                )}
              </div>
            ))}
            {iAmOrganizer && !readOnly && (
              <div className="meet-capture">
                <h4>Google Meet capture</h4>
                {!meetStatus?.configured ? (
                  <p className="reason">Google Meet import needs OAuth credentials configured on the backend.</p>
                ) : (
                  <>
                    <form className="meet-link-form" onSubmit={saveMeetLink}>
                      <label className="note-label">
                        Meet link
                        <input
                          type="url"
                          value={meetUrlInput}
                          onChange={(e) => setMeetUrlInput(e.target.value)}
                          placeholder="https://meet.google.com/abc-defg-hij"
                          required
                        />
                      </label>
                      <button type="submit" disabled={meetSaving || !meetUrlInput.trim()}>
                        {meetSaving ? "Saving…" : "Save Meet link"}
                      </button>
                    </form>
                    <div className="actions">
                      <button onClick={connectGoogleMeet}>
                        {meetStatus.connected ? "Reconnect Google Meet" : "Connect Google Meet"}
                      </button>
                      <span className="reason">
                        {meetStatus.connected ? "Organizer account connected" : "Connect the organizer's Google account"}
                      </span>
                    </div>
                    {meetStatus.connected && meetStatus.meetUrl && (
                      <>
                        <p className="reason">After the meeting ends and Meet generates a transcript, import it here.</p>
                        <button disabled={meetImporting} onClick={importMeetTranscript}>
                          {meetImporting ? "Importing transcript…" : "Import transcript"}
                        </button>
                        <div className="note-readers">
                          <div className="note-readers-head">
                            <span>Transcript readers</span>
                            <button type="button" className="link" onClick={() => setNoteReaders(inviteeIds)}>Select all</button>
                          </div>
                          {inviteeIds.map((id) => (
                            <label className="note-reader" key={id}>
                              <input
                                type="checkbox"
                                checked={noteReaders.includes(id)}
                                onChange={(e) => setNoteReaders((current) => e.target.checked
                                  ? [...current, id]
                                  : current.filter((reader) => reader !== id))}
                              />
                              {name(id)}
                            </label>
                          ))}
                        </div>
                      </>
                    )}
                  </>
                )}
              </div>
            )}
            {iAmOrganizer && !readOnly && (
              <form onSubmit={saveMeetingNote}>
                <label className="note-label">
                  Add a note
                  <textarea
                    rows={4}
                    value={meetingNoteText}
                    onChange={(e) => setMeetingNoteText(e.target.value)}
                    placeholder="Write notes or a handover summary…"
                    required
                  />
                </label>
                <div className="note-readers">
                  <div className="note-readers-head">
                    <span>Choose who can read this note</span>
                    <button type="button" className="link" onClick={() => setNoteReaders(inviteeIds)}>Select all</button>
                  </div>
                  {inviteeIds.map((id) => (
                    <label className="note-reader" key={id}>
                      <input
                        type="checkbox"
                        checked={noteReaders.includes(id)}
                        onChange={(e) => setNoteReaders((current) => e.target.checked
                          ? [...current, id]
                          : current.filter((reader) => reader !== id))}
                      />
                      {name(id)}
                    </label>
                  ))}
                </div>
                <div className="actions">
                  <button className="primary" type="submit" disabled={notesSaving || !meetingNoteText.trim()}>
                    {notesSaving ? "Saving…" : "Save note"}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
      </section>}

      <section className="ai">
        <div className="ai-row">
          <span className="ai-label">Recommendation</span>
          <strong>{ai.recommendation ? label(ai.recommendation) : "Your choice is needed"}</strong>
          <span className={`pill conf-${ai.confidence}`}>{cap(ai.confidence)} confidence</span>
          <AiSource ai={ai} />
        </div>
        <p className="reason">{ai.reason}</p>
        {ai.engine === "analysing" && <div className="skeleton" aria-hidden="true" />}
        <ProxySuggestions ai={ai} declined={declined} name={name} />
        <AgentTrail ai={ai} name={name} />
        <RecommendationDetails ai={ai} />
      </section>

      {((item.chosenProxyId && !afterDecline) || item.decidedBy) && (
        <div className="note">
          {[item.chosenProxyId && !afterDecline && `Proxy: ${name(item.chosenProxyId)}`, item.decidedBy && `Decided by ${name(item.decidedBy)}`]
            .filter(Boolean).join(" · ")}
        </div>
      )}
      {item.rescheduledTo && <div className="note">Moved to {fmtWhen(item.rescheduledTo)}</div>}
      {afterDecline && <div className="note warn">{declineNotice(ai, declined, name)}</div>}
      {item.status === "no_slot_found" && <div className="note warn">No time works for everyone in the next few working days. Please pick a time yourself.</div>}
      {item.status === "awaiting_organizer" && <div className="note">The organizer has been asked to {item.chosenAction}.</div>}


      {!readOnly && !terminal && !showActions && (
        <button className="link" onClick={() => setShowActions(true)}>Review or change</button>
      )}

      {!readOnly && !terminal && showActions && mode === "idle" && (
        <div className="actions">
          {ordered.map((b, n) => {
            const recommended = b.action === highlight;
            const isTaken = b.action === taken;
            // with a recommended or taken action leading, the others are smaller: one clear choice, the rest as options
            const secondary = leads && n > 0;
            const button = (
              <button
                key={b.action}
                // the taken action can't be repeated, except a proxy: clicking it lets you choose someone else
                disabled={busy || (isTaken && b.action !== "proxy")}
                className={[recommended ? "primary lead" : "", isTaken ? "taken" : "", secondary ? "small" : "",
                  b.danger && !isTaken ? "danger" : ""].join(" ").trim()}
                title={isTaken ? (b.action === "proxy" ? "Done. Click to choose someone else." : "Done") : recommended ? "Recommended" : b.hint}
                aria-label={isTaken ? `${takenText[b.action]} (done)` : recommended ? `Recommended: ${b.text}` : b.text}
                onClick={b.onClick}
              >
                {isTaken ? <><Icon name="check" size={15} />{takenText[b.action]}</>
                  : recommended ? <><Icon name="spark" size={15} />{b.text}</> : b.text}
              </button>
            );
            if (n !== 1 || !leads) return button;
            return [<span key="change" className="change-label">{taken ? "or change to:" : "or"}</span>, button];
          })}
          {busy && <span className="saving" role="status">Saving…</span>}
        </div>
      )}

      {mode === "proxy" && (
        <ProxyPanel item={item} me={me} people={people}
          onSent={async () => { setMode("idle"); await refresh(); }} onBack={() => setMode("idle")} />
      )}

      {mode === "confirm" && proposal && (
        <div className="panel">
          {proposal.none ? (
            <p>No suitable time was found in the next working days. You'll need to pick one yourself.</p>
          ) : (
            <p>
              Move to <b>{fmtWhen(proposal.proposedStart)}</b>
              {proposal.flagged ? " (a little off the original time of day)" : ""}? Everyone required is free, and nobody is on leave.
            </p>
          )}
          <div className="actions">
            <button className="primary" disabled={busy} onClick={() => act("reschedule")}>
              {proposal.none ? "Note that no time works" : "Confirm reschedule"}
            </button>
            <button className="link" onClick={() => setMode("idle")}>Back</button>
          </div>
        </div>
      )}

      {activity.length > 0 && (
        <details className="activity">
          <summary>Activity ({activity.length})</summary>
          <ul>
            {activity.map((h) => (
              <li key={h.id}><span className="activity-when">{fmtWhen(h.at)}</span> {h.text || `${name(h.actorId)}: ${h.detail}`}</li>
            ))}
          </ul>
        </details>
      )}

      {error && <div className="note warn">{error}</div>}
    </article>
  );
}
