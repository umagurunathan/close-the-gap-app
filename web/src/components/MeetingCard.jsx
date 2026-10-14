import { useEffect, useState } from "react";
import { api } from "../api.js";
import { actionLabel, statusLabel, urgencyLabel, fmtWhen } from "../format.js";
import Invitees from "./Invitees.jsx";

// "high" -> "High"; also used for sources and rule notes, which the backend sends in lower case.
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
// "gemini-2.5-flash" -> "Gemini 2.5 Flash"
const prettyModel = (m) => (m || "Gemini").split("-").map(cap).join(" ");

// Where the recommendation came from, so nobody mistakes a rule-based answer for an AI one.
// Green = written by Gemini; amber = Gemini's answer that our rules adjusted; grey = written by our rules.
function AiSource({ ai }) {
  const changes = ai.checks?.length ? ai.checks.map(cap).join("\n") : "";
  if (ai.engine === "gemini" && !changes) {
    return <span className="pill src-ai" title="Written by Gemini and checked by our rules; no changes were needed.">✓ {prettyModel(ai.model)}</span>;
  }
  if (ai.engine === "gemini") {
    return (
      <>
        <span className="pill src-ai" title="Written by Gemini.">{prettyModel(ai.model)}</span>
        <span className="pill src-adjusted" title={changes}>Adjusted by rules</span>
      </>
    );
  }
  if (ai.engine === "rules_fallback") {
    return <span className="pill src-rules" title="The AI did not answer in time, so our rules suggested this. The AI will be asked again.">Rule-based · AI unavailable</span>;
  }
  if (ai.engine === "rules_override") {
    return <span className="pill src-rules" title={changes}>Rule-based · AI answer not allowed</span>;
  }
  return <span className="pill src-rules" title="The AI is switched off; this suggestion comes from our rules.">Rule-based</span>;
}

// One card per meeting. Same layout in every tab.
export default function MeetingCard({ item, people, me, role, refresh, quiet = false, readOnly = false, activity = [] }) {
  const [mode, setMode] = useState("idle"); // idle | proxy | confirm
  const [candidates, setCandidates] = useState([]);
  const [pick, setPick] = useState("");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [note, setNote] = useState("");
  const [fromAi, setFromAi] = useState(false);
  const [draftOk, setDraftOk] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [showActions, setShowActions] = useState(!quiet);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const ev = item.event;
  const name = (id) => people[id]?.name ?? id;
  const iAmOrganizer = ev.organizerId === me;
  const terminal = item.status === "rescheduled" || item.status === "cancelled";
  // Planned leave: the leaver decides. Sudden absence: both the absent person and the organizer can act.
  const iDecide = true;
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

  async function act(action, proxyId, extra = {}) {
    setBusy(true);
    setError("");
    try {
      await api(`/items/${item.id}/action`, { method: "POST", person: me, body: { action, proxyId, ...extra } });
      setMode("idle");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function openProxy() {
    setError("");
    try {
      const list = await api(`/items/${item.id}/proxy-candidates`, { person: me });
      setCandidates(list);
      setPick(ai.suggestedProxyId && list.some((c) => c.personId === ai.suggestedProxyId) ? ai.suggestedProxyId : "");
      setNote("");
      setQuery("");
      setMatches([]);
      setFromAi(false);
      // "Draft with AI" is offered only when the host shared the summary with everyone invited
      setDraftOk((await api(`/items/${item.id}/note-draft/available`, { person: me })).available);
      setMode("proxy");
    } catch (e) {
      setError(e.message);
    }
  }

  // Anyone in the company directory can be named, invited or not. The search runs on the server.
  async function searchDirectory(text) {
    setQuery(text);
    if (text.trim().length < 2) return setMatches([]);
    try {
      const day = ev.start.slice(0, 10); // so people on leave that day are flagged
      const found = await api(`/directory?q=${encodeURIComponent(text.trim())}&day=${day}`, { person: me });
      setMatches(found.filter((p) => p.id !== item.absentPersonId));
    } catch (e) {
      setError(e.message);
    }
  }

  const invitedIds = new Set([ev.organizerId, ...ev.attendees.map((a) => a.personId)]);
  const pickedOutsider = pick && !invitedIds.has(pick);
  // An AI draft is built from summaries shared with everyone invited, so it is off for someone who is not invited.
  const canDraft = draftOk && !pickedOutsider;
  // If an AI draft was already written and the sender then picks someone not invited, drop it (it came from summaries
  // that person could not open); the sender writes their own note.
  useEffect(() => {
    if (pickedOutsider && fromAi) {
      setNote("");
      setFromAi(false);
    }
  }, [pickedOutsider, fromAi]);

  async function draftWithAi() {
    setDrafting(true);
    setError("");
    try {
      const { draft } = await api(`/items/${item.id}/note-draft?proxyId=${pick}`, { method: "POST", person: me });
      setNote(draft);
      setFromAi(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setDrafting(false);
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

  // Who wrote the recommendation, in plain words, for the details panel.
  const writtenBy = {
    gemini: `Gemini (${prettyModel(ai.model)}), checked by our rules`,
    rules_fallback: "Our rules (the AI did not answer in time; it will be asked again)",
    rules_override: "Our rules (the AI's answer was not allowed)",
  }[ai.engine] ?? "Our rules (the AI is switched off)";

  // The recommended action comes first and stands out; the others follow in the usual order.
  const firstName = (id) => name(id).split(" ")[0];
  const buttons = [
    mine && item.ownerRole === "leaver" && { action: "attend", text: label("attend"), onClick: () => act("attend") },
    { action: "proceed_without", text: label("proceed_without"), onClick: () => act("proceed_without") },
    {
      action: "proxy",
      text: ai.recommendation === "proxy" && ai.suggestedProxyId ? `Ask ${firstName(ai.suggestedProxyId)} to cover` : "Choose a proxy",
      onClick: openProxy,
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
        <details className="rec-details">
          <summary>Recommendation details</summary>
          <dl>
            <dt>Recommended by</dt>
            <dd>{writtenBy}</dd>
            <dt>Based on</dt>
            <dd>{ai.sources.map(cap).join(" · ")}</dd>
            <dt>Meeting summaries</dt>
            <dd>{ai.summariesAvailable ? "Available to you and used" : "None available to you"}</dd>
            <dt>Adjustments by our rules</dt>
            <dd>
              {ai.checks?.length ? (
                <ul>{ai.checks.map((c, n) => <li key={n}>{cap(c)}</li>)}</ul>
              ) : (
                "None needed"
              )}
            </dd>
          </dl>
        </details>
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

      {!readOnly && !terminal && iDecide && !showActions && (
        <button className="link" onClick={() => setShowActions(true)}>Review or change</button>
      )}

      {!readOnly && !terminal && iDecide && showActions && mode === "idle" && (
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
        <div className="panel">
          <h4>Choose a proxy</h4>
          {candidates.length > 0 && (
            <>
              <select value={candidates.some((c) => c.personId === pick) ? pick : ""} onChange={(e) => setPick(e.target.value)}>
                <option value="">From this meeting's attendees…</option>
                {candidates.map((c) => (
                  <option key={c.personId} value={c.personId}>
                    {name(c.personId)}{c.personId === ai.suggestedProxyId ? " (suggested)" : ""}
                  </option>
                ))}
              </select>
              {pick && candidates.some((c) => c.personId === pick) && (
                <p className="reason">{candidates.find((c) => c.personId === pick)?.reason}</p>
              )}
            </>
          )}
          <input
            type="search"
            value={query}
            placeholder="Or search the company directory by email…"
            onChange={(e) => searchDirectory(e.target.value)}
          />
          {matches.length > 0 && (
            <select value={matches.some((p) => p.id === pick) ? pick : ""} onChange={(e) => setPick(e.target.value)}>
              <option value="">Select from the directory…</option>
              {matches.map((p) => (
                <option key={p.id} value={p.id} disabled={p.out}>
                  {p.email} · {p.name} · {p.title}{p.out ? " (out of office that day)" : invitedIds.has(p.id) ? "" : " (not invited)"}
                </option>
              ))}
            </select>
          )}
          {pickedOutsider && (
            <p className="reason">
              {name(pick)} isn't on this invite. They'll be added as an optional attendee when you send the request.
            </p>
          )}
          <label className="note-label">
            Note for the proxy (optional)
            <textarea
              rows={4}
              value={note}
              placeholder={canDraft ? "Type a note, or use Draft with AI" : "Type your own note for the proxy"}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="actions">
            <button disabled={!canDraft || drafting} onClick={draftWithAi}>
              {drafting ? "Drafting…" : "Draft with AI"}
            </button>
            {fromAi && <span className="reason">Review and edit before sending.</span>}
          </div>
          <div className="actions">
            <button className="primary" disabled={busy || !pick}
              onClick={() => act("proxy", pick, { note, noteFromAi: fromAi })}>Send proxy request</button>
            <button className="link" onClick={() => setMode("idle")}>Back</button>
          </div>
        </div>
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
