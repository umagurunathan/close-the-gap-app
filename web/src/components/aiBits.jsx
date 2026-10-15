// Shared pieces that show the AI's part on a card. Used by the person's card and the organizer's meeting card.

// "high" -> "High"; also used for sources and rule notes, which the backend sends in lower case.
export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
// "gemini-2.5-flash" -> "Gemini 2.5 Flash"
export const prettyModel = (m) => (m || "Gemini").split("-").map(cap).join(" ");
// "list_proxy_candidates" -> "list proxy candidates"
const toolName = (t) => t.replaceAll("_", " ");

// Written by Gemini: either the ADK agent (it chose tools) or one Gemini call.
const isGemini = (ai) => ai.engine === "gemini" || ai.engine === "gemini_adk";
const geminiLabel = (ai) => `${prettyModel(ai.model)}${ai.engine === "gemini_adk" ? " · ADK agent" : ""}`;

// Where the recommendation came from, so nobody mistakes a rule-based answer for an AI one.
// Green = written by Gemini; amber = Gemini's answer that our rules adjusted; grey = written by our rules.
export function AiSource({ ai }) {
  const changes = ai.checks?.length ? ai.checks.map(cap).join("\n") : "";
  const how = ai.engine === "gemini_adk"
    ? `Written by a Gemini agent that looked up: ${(ai.toolsUsed || []).map(toolName).join(", ") || "nothing"}.`
    : "Written by Gemini.";
  if (isGemini(ai) && !changes) {
    return <span className="pill src-ai" title={`${how} Checked by our rules; no changes were needed.`}>✓ {geminiLabel(ai)}</span>;
  }
  if (isGemini(ai)) {
    return (
      <>
        <span className="pill src-ai" title={how}>{geminiLabel(ai)}</span>
        <span className="pill src-adjusted" title={changes}>Adjusted by rules</span>
      </>
    );
  }
  if (ai.engine === "analysing") {
    return <span className="pill src-analysing" title="Gemini is looking at this meeting. Until it answers, this is our rules' suggestion; the card updates by itself.">AI analysing…</span>;
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
    return <span className="pill src-rules" title="A large event where this person has no hosting role: our rules handle it, no AI review is needed.">Rule-based · large event</span>;
  }
  return <span className="pill src-rules" title="The AI is switched off; this suggestion comes from our rules.">Rule-based</span>;
}

// Who wrote the recommendation, in plain words.
export function writtenBy(ai) {
  return {
    gemini_adk: `A Gemini agent (${prettyModel(ai.model)}, built with ADK), checked by our rules`,
    gemini: `Gemini (${prettyModel(ai.model)}), checked by our rules`,
    analysing: "Our rules, for now (Gemini is analysing this meeting; the card updates by itself)",
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
            <b className={declined.includes(id) ? "declined-name" : ""}>{name(id)}</b>
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

// The collapsed "Recommendation details" panel.
export function RecommendationDetails({ ai }) {
  return (
    <details className="rec-details">
      <summary>Recommendation details</summary>
      <dl>
        <dt>Recommended by</dt>
        <dd>{writtenBy(ai)}</dd>
        {ai.toolsUsed?.length > 0 && (
          <>
            <dt>What the agent looked up</dt>
            <dd>{ai.toolsUsed.map((t, n) => <span key={n}>{n > 0 && " → "}{cap(toolName(t))}</span>)}</dd>
          </>
        )}
        <dt>Based on</dt>
        <dd>{ai.sources.map(cap).join(" · ")}</dd>
        <dt>Meeting summaries</dt>
        <dd>{ai.summariesAvailable ? "Available to you and used" : "None available to you"}</dd>
        <dt>Adjustments by our rules</dt>
        <dd>
          {ai.checks?.length ? <ul>{ai.checks.map((c, n) => <li key={n}>{cap(c)}</li>)}</ul> : "None needed"}
        </dd>
      </dl>
    </details>
  );
}
