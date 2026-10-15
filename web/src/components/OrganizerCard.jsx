import { useState } from "react";
import { api } from "../api.js";
import { statusLabel, urgencyLabel, fmtWhen } from "../format.js";
import { AiSource, ProxySuggestions, RecommendationDetails, cap, declineNotice } from "./aiBits.jsx";
import Invitees from "./Invitees.jsx";
import ProxyPanel from "./ProxyPanel.jsx";

// Organizer Mode: ONE card per meeting, naming everyone who is out (Decision 55).
// Meeting-level actions (reschedule, go on without them, cancel) apply to everyone on the card; a proxy is chosen per
// person, on that person's line.
const MEETING_LABEL = {
  reschedule: "Reschedule",
  proceed_without: "Go on without them",
  cancel: "Cancel this meeting",
  proxy: "Arrange a proxy",
  attend: "They'll attend",
};
const DECIDING = ["pending_decision", "proxy_declined", "no_slot_found", "awaiting_organizer"];

export default function OrganizerCard({ meeting, people, me, refresh }) {
  const [proxyFor, setProxyFor] = useState(null); // the item whose proxy panel is open
  const [proposal, setProposal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ev = meeting.event;
  const ai = meeting.ai;
  const people_ = meeting.absentees;
  const name = (id) => people[id]?.name ?? id;
  const first = (id) => name(id).split(" ")[0];
  const terminal = people_.every((a) => a.status === "rescheduled" || a.status === "cancelled");
  const open = people_.filter((a) => a.needsAttention);
  const urgency = urgencyLabel(meeting.urgency, meeting.hoursToStart);
  const attention = meeting.urgency || (meeting.needsAttention ? "open" : "settled");
  const movedTo = people_.find((a) => a.rescheduledTo)?.rescheduledTo;

  const chip = terminal
    ? { cls: `status-${people_[0].status}`, text: statusLabel(people_[0].status, false, "", null) }
    : open.length === 0
      ? { cls: "status-proceeding_without", text: "Settled" }
      : open.length === people_.length
        ? { cls: "status-pending_decision", text: "Not handled yet" }
        : { cls: "status-proxy_requested", text: `${open.length} of ${people_.length} need a decision` };

  async function decide(action) {
    setBusy(true);
    setError("");
    try {
      await api(`/meetings/${ev.calendarEventId}/action`, { method: "POST", person: me, body: { action } });
      setProposal(null);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function askReschedule() {
    setError("");
    try {
      const anyItem = (open[0] ?? people_[0]).id;
      setProposal(await api(`/items/${anyItem}/proposed-time`, { person: me }));
    } catch (e) {
      setError(e.message);
    }
  }

  // Meeting-level buttons; the recommended one comes first and stands out while a decision is needed.
  // after a proxy declined, no button is singled out: it is the organizer's call again
  const allDeclined = open.length > 0 && open.every((a) => a.status === "proxy_declined");
  const highlight = meeting.needsAttention && !allDeclined ? ai.recommendation : null;
  const actions = [
    { action: "reschedule", onClick: askReschedule },
    { action: "proceed_without", onClick: () => decide("proceed_without") },
    { action: "cancel", onClick: () => decide("cancel"), danger: true },
  ];
  // "Go on without them" already chosen for everyone still out: shown in green with a tick, like on the person's card.
  const goingOnWithout = !meeting.needsAttention && !terminal &&
    people_.every((a) => ["proceeding_without", "auto_handled"].includes(a.status));
  const taken = goingOnWithout ? "proceed_without" : null;
  const first_ = taken ?? highlight;
  const ordered = [...actions.filter((b) => b.action === first_), ...actions.filter((b) => b.action !== first_)];

  return (
    <article className={`card attn-${attention}`}>
      <header className="card-head">
        <div>
          <h3>{ev.title}</h3>
          <div className="when">{fmtWhen(ev.start)}</div>
        </div>
        <div className="chips">
          {urgency && <span className={`chip urgency-${meeting.urgency}`}>{urgency}</span>}
          <span className={`chip ${chip.cls}`}>{chip.text}</span>
        </div>
      </header>

      <Invitees event={ev} absentIds={people_.map((a) => a.absentPersonId)} people={people} />

      <section className="ai">
        <div className="ai-row">
          <span className="ai-label">Recommendation</span>
          <strong>{ai.recommendation ? MEETING_LABEL[ai.recommendation] : "Your choice is needed"}</strong>
          <span className={`pill conf-${ai.confidence}`}>{cap(ai.confidence)} confidence</span>
          <AiSource ai={ai} />
        </div>
        <p className="reason">{ai.reason}</p>
        <RecommendationDetails ai={ai} />
      </section>

      <div className="absentees" aria-label="People who are out">
        {people_.map((a) => {
          const deciding = DECIDING.includes(a.status);
          const suggested = a.ai.suggestedProxyId;
          const hasProxy = a.status === "proxy_requested" || a.status === "proxy_accepted";
          const declined = a.declinedProxyIds || [];
          const afterDecline = a.status === "proxy_declined" && declined.length > 0;   // the person's call again
          const stars = deciding && !afterDecline && a.ai.recommendation === "proxy";
          return (
            <div key={a.id} className="absentee">
              <div className="absentee-row">
                <b>{name(a.absentPersonId)}</b>
                <span className={`chip status-${a.status}`}>{statusLabel(a.status, false, first(a.absentPersonId), a.chosenAction)}</span>
                {!terminal && hasProxy && (
                  <button className="taken" title="Done. Click to choose someone else." onClick={() => setProxyFor(a.id)}>
                    {a.status === "proxy_accepted" ? `✓ ${first(a.chosenProxyId)} will cover` : `✓ ${first(a.chosenProxyId)} asked to cover`}
                  </button>
                )}
                {/* A proxy can still be chosen after "go on without them" or "they'll attend": people change their mind.
                    Only while a decision is needed does the AI's suggestion stand out. */}
                {!terminal && !hasProxy && (
                  <button
                    className={stars ? "primary" : ""}
                    aria-label={`Choose a proxy for ${name(a.absentPersonId)}`}
                    onClick={() => setProxyFor(a.id)}
                  >
                    {stars ? "★ " : ""}
                    {afterDecline ? "Choose another proxy" : deciding && suggested ? `Ask ${first(suggested)} to cover` : "Choose a proxy"}
                  </button>
                )}
              </div>
              {!terminal && <ProxySuggestions ai={a.ai} declined={declined} name={name} />}
              {afterDecline && <div className="note warn">{declineNotice(a.ai, declined, name)}</div>}
              {a.decidedBy && <div className="absentee-note">Decided by {name(a.decidedBy)}</div>}
              {proxyFor === a.id && (
                <ProxyPanel item={a} me={me} people={people}
                  onSent={async () => { setProxyFor(null); await refresh(); }} onBack={() => setProxyFor(null)} />
              )}
            </div>
          );
        })}
      </div>

      {movedTo && <div className="note">Moved to {fmtWhen(movedTo)}</div>}

      {!terminal && !proposal && (
        <div className="actions">
          <span className="change-label">For the whole meeting:</span>
          {ordered.map((b, n) => {
            const recommended = b.action === highlight;
            const isTaken = b.action === taken;
            const button = (
              <button key={b.action} disabled={busy || isTaken}
                className={[recommended ? "primary" : "", isTaken ? "taken" : "", b.danger && !isTaken ? "danger" : ""].join(" ").trim()}
                title={isTaken ? "Done" : undefined}
                aria-label={isTaken ? "Going on without them (done)" : recommended ? `Recommended: ${MEETING_LABEL[b.action]}` : MEETING_LABEL[b.action]}
                onClick={b.onClick}>
                {isTaken ? "✓ Going on without them" : `${recommended ? "★ " : ""}${MEETING_LABEL[b.action]}`}
              </button>
            );
            return taken && n === 1 ? [<span key="change" className="change-label">or change to:</span>, button] : button;
          })}
          {busy && <span className="saving" role="status">Saving…</span>}
        </div>
      )}

      {proposal && (
        <div className="panel">
          {proposal.none ? (
            <p>No time works for everyone in the next working days. You'll need to pick one yourself.</p>
          ) : (
            <p>
              Move to <b>{fmtWhen(proposal.proposedStart)}</b>
              {proposal.flagged ? " (a little off the original time of day)" : ""}? Everyone who is out will be back,
              and every key person is free.
            </p>
          )}
          <div className="actions">
            <button className="primary" disabled={busy} onClick={() => decide("reschedule")}>
              {proposal.none ? "Record: no time found" : "Confirm reschedule"}
            </button>
            <button className="link" onClick={() => setProposal(null)}>Back</button>
          </div>
        </div>
      )}

      {error && <div className="note warn">{error}</div>}
    </article>
  );
}
