// Shared pieces that show the AI's part on a card. Used by the person's card and the organizer's meeting card.
import { Icon } from "./Icons.jsx";

// "high" -> "High"; also used for sources and rule notes, which the backend sends in lower case.
export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
// "gemini-2.5-flash" -> "Gemini 2.5 Flash"
export const prettyModel = (m) => (m || "Gemini").split("-").map(cap).join(" ");
// "list_proxy_candidates" -> "list proxy candidates"
const toolName = (t) => t.replaceAll("_", " ");

// What simple rules alone would have said, and whether the AI's answer differs from it (the difference the AI makes).
const RULE_ACTION = { proxy: "Arrange a proxy", reschedule: "Reschedule", proceed_without: "Go on without them",
  cancel: "Cancel", attend: "Attend" };
const RULE_KIND = { team_checkin: "a routine team check-in", org_event: "an org-wide event" };
export function aiChangedAnswer(ai) {
  const r = ai.rulesAnswer;
  if (!r || !(ai.engine === "gemini" || ai.engine === "gemini_adk")) return false;
  return r.recommendation !== ai.recommendation || (r.kind && ai.kind && r.kind !== ai.kind)
    || (ai.recommendation === "proxy" && r.suggestedProxyId && r.suggestedProxyId !== ai.suggestedProxyId);
}
function rulesSummary(r, name) {
  const parts = [RULE_ACTION[r.recommendation] ?? "No recommendation"];
  if (RULE_KIND[r.kind]) parts.push(`it looks like ${RULE_KIND[r.kind]}`);
  if (r.recommendation === "proxy" && r.suggestedProxyId) parts.push(`proxy ${name(r.suggestedProxyId)}`);
  return parts.join(" · ");
}

// Written by Gemini: either the ADK agent (it chose tools) or one Gemini call.
const isGemini = (ai) => ai.engine === "gemini" || ai.engine === "gemini_adk";
// The pill stays short ("Gemini · ADK agent") so the row fits on one line; the exact model is in its hover and in the details.
const geminiLabel = (ai) => (ai.engine === "gemini_adk" ? "Gemini · ADK agent" : "Gemini");

// Where the recommendation came from, so nobody mistakes a rule-based answer for an AI one.
// Green = written by Gemini; amber = Gemini's answer that our rules adjusted; grey = written by our rules.
export function AiSource({ ai }) {
  const changes = ai.checks?.length ? ai.checks.map(cap).join("\n") : "";
  const how = ai.engine === "gemini_adk"
    ? `Written by a Gemini agent (${prettyModel(ai.model)}, built with ADK) that looked up: ${(ai.toolsUsed || []).map(toolName).join(", ") || "nothing"}.`
    : `Written by ${prettyModel(ai.model)}.`;
  const changed = aiChangedAnswer(ai) && (
    <span className="pill src-changed" title="Simple rules alone would have recommended something else; see Recommendation details.">
      AI changed the answer
    </span>
  );
  if (isGemini(ai) && !changes) {
    return (
      <>
        <span className="pill src-ai" title={`${how} Checked by our rules; no changes were needed.`}><Icon name="check" size={13} />{geminiLabel(ai)}</span>
        {changed}
      </>
    );
  }
  if (isGemini(ai)) {
    return (
      <>
        <span className="pill src-ai" title={how}>{geminiLabel(ai)}</span>
        <span className="pill src-adjusted" title={changes}>Adjusted by rules</span>
        {changed}
      </>
    );
  }
  if (ai.engine === "analysing") {
    return <span className="pill src-analysing" title="Gemini is looking at this meeting. Until it answers, this is our rules' suggestion; the card updates by itself."><Icon name="spark" size={12} />AI analyzing…</span>;
  }
  if (ai.engine === "mixed") {
    return <span className="pill src-adjusted" title="Combined from recommendations written partly by Gemini and partly by our rules.">Gemini and rules</span>;
  }
  if (ai.engine === "rules_fallback") {
    return <span className="pill src-rules" title="The AI did not answer in time, so our rules suggested this. The AI will be asked again.">Rule-based · AI unavailable</span>;
  }
  if (ai.engine === "rules_override") {
    return <span className="pill src-rules" title={changes}>Rule-based · AI answer not allowed</span>;
  }
  if (ai.engine === "rules_policy") {
    return <span className="pill src-rules" title="A large event where this person has no hosting role: our rules handle it, so no AI review is needed.">Rule-based · large event</span>;
  }
  return <span className="pill src-rules" title="The AI is switched off; this suggestion comes from our rules.">Rule-based</span>;
}

// Who wrote the recommendation, in plain words.
export function writtenBy(ai) {
  return {
    gemini_adk: `A Gemini agent (${prettyModel(ai.model)}, built with ADK), checked by our rules`,
    gemini: `Gemini (${prettyModel(ai.model)}), checked by our rules`,
    analysing: "Our rules, for now (Gemini is analyzing this meeting; the card updates by itself)",
    mixed: "Gemini and our rules (combined from each absent person's recommendation)",
    rules_fallback: "Our rules (the AI did not answer in time; it will be asked again)",
    rules_override: "Our rules (the AI's answer was not allowed)",
    rules_policy: "Our rules (large event and no hosting role: no AI review needed)",
  }[ai.engine] ?? "Our rules (the AI is switched off)";
}

// "Suggested proxies: Meena (first choice) · Dev (second choice)". Anyone who declined is marked so.
export function ProxySuggestions({ ai, declined = [], name }) {
  const picks = [[ai.suggestedProxyId, "first choice"], [ai.backupProxyId, "second choice"]].filter(([id]) => id);
  if (!picks.length) {
    return ai.recommendation === "proxy" && ai.needsHumanChoice
      ? <div className="meta"><span>No clear proxy. Please choose one.</span></div>
      : null;
  }
  return (
    <div className="meta">
      <span>
        {picks.length > 1 ? "Suggested proxies: " : "Suggested proxy: "}
        {picks.map(([id, label], n) => (
          <span key={id}>
            {n > 0 && " · "}
            <b className={declined.includes(id) ? "declined-name" : "proxy-name"}>{name(id)}</b>
            {picks.length > 1 && ` (${label}${declined.includes(id) ? ", declined" : ""})`}
            {picks.length === 1 && declined.includes(id) && " (declined)"}
          </span>
        ))}
      </span>
    </div>
  );
}

// After a decline: "Meena declined. Second choice: Dev. Please choose a proxy or take a different action."
// No new AI call: the second choice was given with the first.
export function declineNotice(ai, declined, name) {
  if (!declined.length) return null;
  const first = (id) => name(id).split(" ")[0];
  const names = declined.map(first);
  const who = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
  const next = [ai.suggestedProxyId, ai.backupProxyId].find((id) => id && !declined.includes(id));
  const nextIsBackup = next && next === ai.backupProxyId && declined.includes(ai.suggestedProxyId);
  return `${who} declined.${nextIsBackup ? ` Second choice: ${first(next)}.` : ""} Please choose a proxy or take a different action.`;
}

// What happened to the meeting summaries: the agent chooses its tools, so it may not have read them.
function summariesLine(ai) {
  if (!ai.summariesAvailable) return "None available to you";
  if (ai.engine === "gemini_adk" && !(ai.toolsUsed || []).includes("read_summaries")) {
    return "Available to you, but the agent didn't read them this time";
  }
  return "Available to you and used";
}

// The agent's steps and, when it differs, what simple rules alone would have said: shown on the card, not hidden in
// "Recommendation details", because they are the reason to trust (or question) the answer.
const TOOL_STEP = {
  read_summaries: ["doc", "Read past summaries"],
  list_proxy_candidates: ["users", "Listed proxy candidates"],
  check_if_out: ["calendar", "Checked who's out"],
};
export function AgentTrail({ ai, name = (id) => id }) {
  const tools = ai.engine === "gemini_adk" ? [...new Set(ai.toolsUsed || [])] : [];
  const changed = aiChangedAnswer(ai);
  if (!tools.length && !changed) return null;
  return (
    <>
      {tools.length > 0 && (
        <div className="trail">
          <span>The agent:</span>
          {tools.map((t) => {
            const [icon, text] = TOOL_STEP[t] ?? ["doc", cap(toolName(t))];
            return <span key={t} className="trail-step"><Icon name={icon} size={13} />{text}</span>;
          })}
          <span className="trail-step">
            <Icon name="shield" size={13} />{ai.checks?.length ? "Adjusted by our rules" : "Checked by our rules"}
          </span>
        </div>
      )}
      {changed && (
        <div className="without-ai">
          Without AI, simple rules would have said: <b>{rulesSummary(ai.rulesAnswer, name)}</b>. They match words in
          the title and summaries; Gemini reads what they mean.
        </div>
      )}
    </>
  );
}

// The collapsed "Recommendation details" panel. The summaries and agenda themselves open from the card's
// "Summaries & agenda" link (one way in, Uma).
export function RecommendationDetails({ ai }) {
  return (
    <details className="rec-details">
      <summary>Recommendation details</summary>
      <dl>
        <dt>Recommended by</dt>
        <dd>{writtenBy(ai)}</dd>
        <dt>Based on</dt>
        <dd>{ai.sources.map(cap).join(" · ")}</dd>
        <dt>Meeting summaries</dt>
        <dd>{summariesLine(ai)}</dd>
        <dt>Adjustments by our rules</dt>
        <dd>
          {ai.checks?.length ? <ul>{ai.checks.map((c, n) => <li key={n}>{cap(c)}</li>)}</ul> : "None needed"}
        </dd>
      </dl>
    </details>
  );
}
