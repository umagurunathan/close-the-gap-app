import { useCallback, useState } from "react";
import { api } from "../api.js";
import { statusLabel, urgencyChip, fmtWhen } from "../format.js";
import { AgentTrail, AiSource, ProxySuggestions, RecommendationDetails, cap, declineNotice } from "./aiBits.jsx";
import { Icon } from "./Icons.jsx";
import Invitees from "./Invitees.jsx";
import ProxyPanel from "./ProxyPanel.jsx";
import ReschedulePanel from "./ReschedulePanel.jsx";
import SummariesDialog, { SummariesLink } from "./Summaries.jsx";

// Organizer Mode: ONE card per meeting, naming everyone who is out.
// Meeting-level actions (reschedule, go on without them, cancel) apply to everyone on the card ("For everyone who is
// out:" when there are several); a proxy is chosen per person, on that person's line.
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
  const [showSummaries, setShowSummaries] = useState(false);
  const openSummaries = useCallback(() => setShowSummaries(true), []);
  const closeSummaries = useCallback(() => setShowSummaries(false), []);

  const ev = meeting.event;
  const ai = meeting.ai;
  const people_ = meeting.absentees;
  const name = (id) => people[id]?.name ?? id;
  const first = (id) => name(id).split(" ")[0];
  const terminal = people_.every((a) => a.status === "rescheduled" || a.status === "cancelled");
  const open = people_.filter((a) => a.needsAttention);
  const urgency = urgencyChip(meeting.urgency, meeting.hoursToStart);
  const attention = meeting.urgency || (meeting.needsAttention ? "open" : "settled");
  const movedTo = people_.find((a) => a.rescheduledTo)?.rescheduledTo;

  const chip = terminal
    ? { cls: `status-${people_[0].status}`, text: statusLabel(people_[0].status, false, "", null) }
    : open.length === 0
      ? { cls: "status-proceeding_without", text: "Settled" }
      : open.length === people_.length
        ? { cls: "status-pending_decision", text: "Not handled yet" }
        : { cls: "status-proxy_requested", text: `${open.length} of ${people_.length} need a decision` };

  async function decide(action, start = null) {
    setBusy(true);
    setError("");
    try {
      await api(`/meetings/${ev.calendarEventId}/action`, { method: "POST", person: me, body: { action, start } });
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
  // while a proxy panel is open, the whole-meeting buttons stay (smaller, none singled out) after "Or instead:"
  const choosing = Boolean(proxyFor);
  const highlight = meeting.needsAttention && !allDeclined && !choosing ? ai.recommendation : null;
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
  const leads = Boolean(first_) && ordered[0]?.action === first_;   // one button leads; the rest are smaller
  // a proxy recommendation leads on the person's line, so the whole-meeting buttons are all the smaller options
  const allSmall = choosing || (!leads && highlight === "proxy");
  const several = people_.length > 1;
  // "Or instead:" only while nothing was chosen yet; after a choice the row already reads "✓ … or change to:"
  const actionsLabel = choosing && !goingOnWithout ? (several ? "Or instead, for everyone who is out:" : "Or instead:")
    : several ? "For everyone who is out:" : null;

  return (
    <article className={`card attn-${attention}`}>
      <header className="card-head">
        <div>
          <h3>{ev.title}</h3>
          <div className="when"><Icon name="calendar" size={14} />{fmtWhen(ev.start)}</div>
        </div>
        <div className="chips">
          {urgency && <span className={`chip ${urgency.cls}`}>{urgency.text}</span>}
          {/* "Not handled yet" is not shown: the Needs action group already says so */}
          {chip.text !== "Not handled yet" && <span className={`chip ${chip.cls}`}>{chip.text}</span>}
        </div>
      </header>

      <Invitees event={ev} absentIds={people_.map((a) => a.absentPersonId)} people={people}
        extra={<SummariesLink onOpen={openSummaries} />} />
      {/* the summaries belong to the meeting, so any of its cards gives access to them */}
      {showSummaries && <SummariesDialog itemId={people_[0].id} event={ev} people={people} me={me}
        readOnly={terminal} refresh={refresh} onClose={closeSummaries} />}

      <section className="ai">
        <div className="ai-row">
          <span className="ai-label">Recommendation</span>
          <strong>{ai.recommendation ? MEETING_LABEL[ai.recommendation] : "Your choice is needed"}</strong>
          <span className={`pill conf-${ai.confidence}`}>{cap(ai.confidence)} confidence</span>
          <AiSource ai={ai} />
        </div>
        <p className="reason">{ai.reason}</p>
        {ai.engine === "analysing" && <div className="skeleton" aria-hidden="true" />}
        <AgentTrail ai={ai} name={name} />
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
                {/* per person; "Not handled yet" only matters when several people are out */}
                {(a.status !== "pending_decision" || people_.length > 1) && (
                  <span className={`chip status-${a.status}`}>{statusLabel(a.status, false, first(a.absentPersonId), a.chosenAction)}</span>
                )}
                {!terminal && hasProxy && (
                  <button className="taken" title="Done. Click to choose someone else." onClick={() => setProxyFor(a.id)}>
                    <Icon name="check" size={15} />
                    {a.status === "proxy_accepted" ? `${first(a.chosenProxyId)} will cover` : `${first(a.chosenProxyId)} asked to cover`}
                  </button>
                )}
                {/* A proxy can still be chosen after "go on without them" or "they'll attend": people change their mind.
                    Only while a decision is needed does the AI's suggestion stand out. */}
                {!terminal && !hasProxy && proxyFor !== a.id && (
                  <button
                    className={stars ? "primary" : ""}
                    aria-label={`Choose a proxy for ${name(a.absentPersonId)}`}
                    onClick={() => setProxyFor(a.id)}
                  >
                    {stars && <Icon name="spark" size={15} />}
                    {afterDecline ? "Choose another proxy" : deciding && suggested ? `Ask ${first(suggested)} to cover` : "Choose a proxy"}
                  </button>
                )}
              </div>
              {!terminal && <ProxySuggestions ai={a.ai} declined={declined} name={name} />}
              {afterDecline && <div className="note warn">{declineNotice(a.ai, declined, name)}</div>}
              {a.decidedBy && (
                <div className="absentee-note">
                  {declined.length > 0 && !afterDecline && `${declined.map(name).join(", ")} declined to cover · `}
                  Decided by {name(a.decidedBy)}
                </div>
              )}
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
          {/* only with several people out does it matter that these act for all of them (a proxy is per person) */}
          {actionsLabel && <span className="change-label">{actionsLabel}</span>}
          {ordered.map((b, n) => {
            const recommended = b.action === highlight;
            const isTaken = b.action === taken;
            const button = (
              <button key={b.action} disabled={busy || isTaken}
                className={[recommended ? "primary lead" : "", isTaken ? "taken" : "", (leads && n > 0) || allSmall ? "small" : "",
                  b.danger && !isTaken ? "danger" : ""].join(" ").trim()}
                title={isTaken ? "Done" : undefined}
                aria-label={isTaken ? "Going on without them (done)" : recommended ? `Recommended: ${MEETING_LABEL[b.action]}` : MEETING_LABEL[b.action]}
                onClick={b.onClick}>
                {isTaken ? <><Icon name="check" size={15} />Going on without them</>
                  : recommended ? <><Icon name="spark" size={15} />{MEETING_LABEL[b.action]}</> : MEETING_LABEL[b.action]}
              </button>
            );
            if (n !== 1 || !leads) return button;
            return [<span key="change" className="change-label">{taken ? "or change to:" : "or"}</span>, button];
          })}
          {busy && <span className="saving" role="status">Saving…</span>}
        </div>
      )}

      {proposal && (
        <ReschedulePanel proposal={proposal} currentStart={ev.start} busy={busy}
          onConfirm={(start) => decide("reschedule", start)} onBack={() => setProposal(null)} />
      )}

      {error && <div className="note warn">{error}</div>}
    </article>
  );
}
