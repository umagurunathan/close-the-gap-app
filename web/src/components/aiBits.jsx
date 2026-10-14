// Shared pieces that show the AI's part on a card. Used by the person's card and the organizer's meeting card.

// "high" -> "High"; also used for sources and rule notes, which the backend sends in lower case.
export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
// "gemini-2.5-flash" -> "Gemini 2.5 Flash"
export const prettyModel = (m) => (m || "Gemini").split("-").map(cap).join(" ");

// Where the recommendation came from, so nobody mistakes a rule-based answer for an AI one.
// Green = written by Gemini; amber = Gemini's answer that our rules adjusted; grey = written by our rules.
export function AiSource({ ai }) {
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
    gemini: `Gemini (${prettyModel(ai.model)}), checked by our rules`,
    mixed: "Gemini and our rules (combined from each absent person's recommendation)",
    rules_fallback: "Our rules (the AI did not answer in time; it will be asked again)",
    rules_override: "Our rules (the AI's answer was not allowed)",
    rules_policy: "Our rules (large event and no hosting role: no AI review needed)",
  }[ai.engine] ?? "Our rules (the AI is switched off)";
}

// The collapsed "Recommendation details" panel.
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
        <dd>{ai.summariesAvailable ? "Available to you and used" : "None available to you"}</dd>
        <dt>Adjustments by our rules</dt>
        <dd>
          {ai.checks?.length ? <ul>{ai.checks.map((c, n) => <li key={n}>{cap(c)}</li>)}</ul> : "None needed"}
        </dd>
      </dl>
    </details>
  );
}
