import { useCallback, useState } from "react";
import { api } from "../api.js";
import { actionLabel, statusLabel, urgencyLabel, fmtWhen } from "../format.js";
import { AgentTrail, AiSource, ProxySuggestions, RecommendationDetails, cap, declineNotice } from "./aiBits.jsx";
import { Icon } from "./Icons.jsx";
import Invitees from "./Invitees.jsx";
import ProxyPanel from "./ProxyPanel.jsx";
import SummariesDialog, { SummariesLink } from "./Summaries.jsx";

// One card per (meeting, absent person). Used in Attendee Mode and Past. The organizer sees OrganizerCard instead.
export default function MeetingCard({ item, people, me, role, refresh, quiet = false, readOnly = false, activity = [] }) {
  const [mode, setMode] = useState("idle"); // idle | proxy | confirm
  const [proposal, setProposal] = useState(null);
  const [showActions, setShowActions] = useState(!quiet);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSummaries, setShowSummaries] = useState(false);
  const closeSummaries = useCallback(() => setShowSummaries(false), []);

  const ev = item.event;
  const name = (id) => people[id]?.name ?? id;
  // Summaries and the agenda are for the meeting's invitees (and its organizer) only
  const canSeeSummaries = ev.organizerId === me || ev.attendees.some((a) => a.personId === me);
  const openSummaries = canSeeSummaries ? () => setShowSummaries(true) : null;
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

      <Invitees event={ev} absentId={item.absentPersonId} people={people} alsoActsId={alsoActsId}
        extra={openSummaries && <SummariesLink onOpen={openSummaries} />} />
      {showSummaries && <SummariesDialog itemId={item.id} event={ev} people={people} me={me} readOnly={readOnly}
        refresh={refresh} onClose={closeSummaries} />}

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
        <RecommendationDetails ai={ai} onSummaries={openSummaries} />
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
