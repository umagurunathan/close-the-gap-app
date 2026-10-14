import { useState } from "react";
import { api } from "../api.js";
import { actionLabel, statusLabel, urgencyLabel, fmtWhen } from "../format.js";
import { AiSource, RecommendationDetails, cap } from "./aiBits.jsx";
import Invitees from "./Invitees.jsx";
import ProxyPanel from "./ProxyPanel.jsx";

// One card per (meeting, absent person). Used in Attendee Mode and Past. The organizer sees OrganizerCard instead.
export default function MeetingCard({ item, people, me, role, refresh, quiet = false, readOnly = false, activity = [] }) {
  const [mode, setMode] = useState("idle"); // idle | proxy | confirm
  const [proposal, setProposal] = useState(null);
  const [showActions, setShowActions] = useState(!quiet);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const ev = item.event;
  const name = (id) => people[id]?.name ?? id;
  const iAmOrganizer = ev.organizerId === me;
  const terminal = item.status === "rescheduled" || item.status === "cancelled";
  // Both sides can act: the absent person sees the organizer can too, and vice versa.
  const otherSideNote =
    role === "attendee"
      ? ev.organizerId !== me && `${name(ev.organizerId)} (organizer) can also act on this meeting.`
      : `${name(item.absentPersonId)} can also act on this meeting.`;
  const organizerTag = ev.organizerId === item.absentPersonId;
  const ai = item.ai;
  // "me" = the absent person is the one looking; otherwise labels use their first name
  const mine = item.absentPersonId === me;
  const who = name(item.absentPersonId).split(" ")[0];
  const label = (a) => actionLabel(a, mine, who);
  const urgency = urgencyLabel(item.urgency, item.hoursToStart); // amber within 3 days, red within 24 hours

  async function act(action) {
    setBusy(true);
    setError("");
    try {
      await api(`/items/${item.id}/action`, { method: "POST", person: me, body: { action } });
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
  const buttons = [
    mine && item.ownerRole === "leaver" && { action: "attend", text: label("attend"), onClick: () => act("attend") },
    { action: "proceed_without", text: label("proceed_without"), onClick: () => act("proceed_without") },
    {
      action: "proxy",
      text: ai.recommendation === "proxy" && ai.suggestedProxyId ? `Ask ${firstName(ai.suggestedProxyId)} to cover` : "Choose a proxy",
      onClick: () => setMode("proxy"),
    },
    { action: "reschedule", text: iAmOrganizer ? "Reschedule" : "Ask organizer to reschedule", onClick: onReschedule },
    { action: "cancel", text: iAmOrganizer ? "Cancel this meeting" : "Ask organizer to cancel", onClick: () => act("cancel"), danger: true },
  ].filter(Boolean);
  // Only point at the recommendation while a decision is still needed (not after someone already acted on it).
  const deciding = ["pending_decision", "proxy_declined", "no_slot_found"].includes(item.status);
  const highlight = deciding ? ai.recommendation : null;
  // Once someone has acted, that action comes first in green with a tick and says what happened; the rest stay
  // available after "or change to:", because people may change their mind.
  const taken = !deciding && item.chosenAction ? item.chosenAction : null;
  const proxyFirst = item.chosenProxyId ? firstName(item.chosenProxyId) : "";
  const takenText = {
    proxy: item.status === "proxy_accepted" ? `✓ ${proxyFirst} will cover` : `✓ ${proxyFirst} asked to cover`,
    proceed_without: mine ? "✓ Going on without you" : `✓ Going on without ${who}`,
    attend: "✓ You'll attend",
    reschedule: "✓ Organizer asked to reschedule",
    cancel: "✓ Organizer asked to cancel",
  };
  const first = taken ?? highlight;
  const ordered = [...buttons.filter((b) => b.action === first), ...buttons.filter((b) => b.action !== first)];
  const attention = item.urgency || (item.needsAttention ? "open" : "settled");

  return (
    <article className={`card kind-${item.kind} attn-${attention}`}>
      <header className="card-head">
        <div>
          <h3>{ev.title}</h3>
          <div className="when">{fmtWhen(ev.start)}</div>
        </div>
        <div className="chips">
          {organizerTag && <span className="chip chip-tag">Organizer</span>}
          {urgency && <span className={`chip urgency-${item.urgency}`}>{urgency}</span>}
          <span className={`chip status-${item.status}`}>{statusLabel(item.status, mine, who, item.chosenAction)}</span>
        </div>
      </header>

      <Invitees event={ev} absentId={item.absentPersonId} people={people} />

      <section className="ai">
        <div className="ai-row">
          <span className="ai-label">Recommendation</span>
          <strong>{ai.recommendation ? label(ai.recommendation) : "Your choice is needed"}</strong>
          <span className={`pill conf-${ai.confidence}`}>{cap(ai.confidence)} confidence</span>
          <AiSource ai={ai} />
        </div>
        <p className="reason">{ai.reason}</p>
        {ai.suggestedProxyId ? (
          <div className="meta"><span>Suggested proxy: <b>{name(ai.suggestedProxyId)}</b></span></div>
        ) : ai.recommendation === "proxy" && ai.needsHumanChoice ? (
          <div className="meta"><span>No clear proxy. Please choose one.</span></div>
        ) : null}
        <RecommendationDetails ai={ai} />
      </section>

      {(item.chosenProxyId || item.decidedBy) && (
        <div className="note">
          {[item.chosenProxyId && `Proxy: ${name(item.chosenProxyId)}`, item.decidedBy && `Decided by ${name(item.decidedBy)}`]
            .filter(Boolean).join(" · ")}
        </div>
      )}
      {item.rescheduledTo && <div className="note">Moved to {fmtWhen(item.rescheduledTo)}</div>}
      {item.status === "no_slot_found" && <div className="note warn">No time works for everyone in the next working days. Please pick a time in your calendar.</div>}
      {item.status === "awaiting_organizer" && <div className="note">The organizer has been asked to {item.chosenAction}.</div>}

      {!readOnly && !terminal && otherSideNote && <div className="note muted">{otherSideNote}</div>}

      {!readOnly && !terminal && !showActions && (
        <button className="link" onClick={() => setShowActions(true)}>Review or change</button>
      )}

      {!readOnly && !terminal && showActions && mode === "idle" && (
        <div className="actions">
          {ordered.map((b, n) => {
            const recommended = b.action === highlight;
            const isTaken = b.action === taken;
            const button = (
              <button
                key={b.action}
                // the taken action can't be repeated, except a proxy: clicking it lets you choose someone else
                disabled={busy || (isTaken && b.action !== "proxy")}
                className={[recommended ? "primary" : "", isTaken ? "taken" : "", b.danger && !isTaken ? "danger" : ""].join(" ").trim()}
                title={isTaken ? (b.action === "proxy" ? "Done. Click to choose someone else." : "Done") : recommended ? "Recommended" : undefined}
                aria-label={isTaken ? `${takenText[b.action]} (done)` : recommended ? `Recommended: ${b.text}` : b.text}
                onClick={b.onClick}
              >
                {isTaken ? takenText[b.action] : `${recommended ? "★ " : ""}${b.text}`}
              </button>
            );
            return taken && n === 1 ? [<span key="change" className="change-label">or change to:</span>, button] : button;
          })}
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
              {proposal.none ? "Record: no time found" : "Confirm reschedule"}
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
              <li key={h.id}>{fmtWhen(h.at)} · {name(h.actorId)} · {h.type} · {h.detail}</li>
            ))}
          </ul>
        </details>
      )}

      {error && <div className="note warn">{error}</div>}
    </article>
  );
}
