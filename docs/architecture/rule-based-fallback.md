---
type: Architecture Component
title: Rule-based fallback
description: The keyword rules in agents/fallback/ that answer when the AI is off or unavailable, give every card a first answer while Gemini works, and show what simple rules would have said; plus the legacy Vertex proxy ranker.
resource: ../../backend/agents/fallback/rules_recommender.py
tags: [fallback, rules, ai-off, tests]
sources:
  - resource: ../../backend/agents/fallback/__init__.py
  - resource: ../../backend/agents/fallback/rules_recommender.py
  - resource: ../../backend/agents/fallback/candidate_order.py
  - resource: ../../backend/agents/fallback/simple_note.py
  - resource: ../../backend/agents/vertex_proxy_ranker.py
  - resource: ../../backend/config/settings.toml
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Rule-based fallback (`agents/fallback/`)

The product's judgment runs on Gemini. These plain keyword rules have four jobs:
1. keep the app working when the AI is **off** (tests, `AI_ENABLED=false`) or **unavailable**;
2. give every card a **first answer** at once while Gemini works ("AI analyzing…");
3. show **what simple rules would have said** on every AI card (`AiResult.rulesAnswer`), so "AI changed the answer" is visible;
4. order the people in the proxy panel.

They have the **same signature and result type** as the AI recommender, so swapping between them is a config flip.

## `rules_recommender.recommend(event, absent, people, notes)`

It reads only the viewer's visible notes. It runs in this order:

| # | Condition | Kind / action / confidence |
|---|---|---|
| 1 | Large event and the absent person has a hosting role | `key_meeting` / `proxy` (top-ranked) / medium |
| 2 | Large event otherwise | `org_event` / `proceed_without` / high |
| 3 | Title has a `team_checkin_title_words` entry, summaries exist and contain no `decision_words` ("no decision(s)" is stripped first) | `team_checkin` / `proceed_without` / high |
| 4 | Routine title, no summaries | `key_meeting` / `proceed_without` / medium ("please check") |
| 5 | (Optional) `LLM_PROVIDER=vertex` and notes exist: the legacy ranker suggests a proxy with an exact quote as evidence | `key_meeting` / `proxy` |
| 6 | The absent person is named in summaries with decision words, and the top proxy scores ≥ `min_proxy_score_for_high_confidence` (10) | `key_meeting` / `proxy` / high |
| 7 | The absent person owns a decision otherwise | `key_meeting` / `reschedule` / medium, `needsHumanChoice` |
| 8 | Summaries exist (no owned decision) | `proxy` (or `reschedule` if nobody is ranked) / medium |
| 9 | No summaries; the top candidate has a reporting-line link | `proxy` / low |
| 10 | Nothing | `reschedule` / low, `needsHumanChoice` |

In every step the small-meeting counterpart organizer is removed from the ranking. The second choice is the next-ranked person, if their score is above 0. **Recurrence is deliberately not used.**

What the rules **cannot** read, and the reason the AI exists:
- "no decisions" vs "decision";
- a "sync" that is really a sign-off;
- a customer who insists on one person;
- a handover *from* vs *to* someone;
- "Rohan usually stands in", combined with the fact that Rohan is out.

## `candidate_order.rank_proxies`

This sets the proxy panel's order and the rules' choice. The score is:
- named in visible summaries: 10 + 1 per mention;
- the absent person's manager: +3;
- a peer under the same manager: +2;
- a direct report: +2.

Each candidate gets a plain-words reason. See [Proxy](../concepts/proxy.md).

## `simple_note.draft_note_rules`

The handover note without AI. It uses the summary sentences that mention the absent person or a `[drafter] key_words` word, falling back to the first `fallback_sentences` (2), capped at `max_bullets` (5). The greeting and closing are the same as the Gemini brief.

## Legacy: `agents/vertex_proxy_ranker.py`

`suggest_proxy` is an older optional ranker, used **only** inside the rules fallback when `LLM_PROVIDER=vertex`, which is off by default. It:
- calls its own Gemini client with `GEMINI_MODEL` (default `gemini-3.8-flash`) in `VERTEX_AI_LOCATION` (default `asia-southeast1`);
- rejects any person who is not a candidate;
- rejects any evidence quote that is not an exact substring of a supplied note.

The live app does not use it. Its model and region defaults differ from `[ai]`. See [Known quirks](../operations/known-quirks.md).

## Related
- [Recommendation pipeline](recommendation-pipeline.md)
- [Settings (`[recommendation]`, `[proxy_ranking]`, `[drafter]`)](../config/settings-toml.md)
