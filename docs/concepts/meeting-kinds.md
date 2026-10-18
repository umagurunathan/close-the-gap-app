---
type: Product Concept
title: Meeting kinds
description: Every card is a key meeting (a person decides), a team check-in or an org-wide event (both auto-handled when confident); how the kind is chosen and why it only ever moves up.
resource: ../../backend/app/models.py
tags: [kind, classification, auto-handling]
sources:
  - resource: ../../backend/app/models.py
  - resource: ../../backend/agents/guard.py
  - resource: ../../backend/agents/fallback/rules_recommender.py
  - resource: ../../backend/agents/recommender_ai.py
  - resource: ../../backend/app/service.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Meeting kinds (`ItemKind`)

Every card is classified as one of three kinds. Only `key_meeting` needs a person to decide. The other two are set to `auto_handled` with action `proceed_without` when the card is created, and they wait in **No action needed**, where anyone can still change them.

| Kind | Meaning | Auto-handled? |
|---|---|---|
| `key_meeting` | Everything else: a person must decide | No: `pending_decision` |
| `team_checkin` | A stand-up or status sync where the absence changes nothing | Yes, with high confidence **and** summaries showing status updates only |
| `org_event` | A town hall, talk or site-wide event for a large audience | Yes, unless the absent person organizes, hosts, speaks or presents |

## How the kind is decided

1. **At creation** the card gets the *rules'* answer (`[ai] analyse_on_creation = false`), so creating an absence never waits for the AI. The kind is judged from **the absent person's view** of the summaries.
2. The AI analysis is queued in the background (`analyse_in_background_on_creation = true`).
3. The AI's kind passes through the [guard](../architecture/guard.md). These rules can only push a meeting *towards* `key_meeting`:
   - **Rule 5:** a `team_checkin` with no summaries becomes `key_meeting`.
   - **Rule 7:** an `org_event` where the absent person has a hosting role becomes `key_meeting`.
   - **Rule 8:** a routine kind with any action other than `proceed_without` becomes `key_meeting`.
   - **Rule 10:** text that looks like prompt injection forces `key_meeting`.
   - **Rule 6:** a routine kind below `[ai] auto_handle_requires` ("high") confidence becomes `key_meeting`.
4. **The AI may raise, never lower** (`Service._maybe_raise`, `[ai] ai_may_raise_to_key_meeting = true`). An auto-handled card is moved up to `key_meeting` / `pending_decision` only when all of these hold:
   - Gemini answered (engine `gemini` or `gemini_adk`);
   - the answer was judged from the absent person's own view;
   - nobody has decided yet.

   It is logged as `ai_raised`. A card is never moved *down*: the AI never hides a card on its own.

## The rule-based stand-in (fallback)

`agents/fallback/rules_recommender.recommend`:
- **Large event** (group list, or more than 35 required): `org_event` / `proceed_without`, high confidence, unless the absent person has a hosting role, in which case `key_meeting` / `proxy`.
- **Routine title words** (`stand-up`, `standup`, `dsu`, `sync`, `check-in`…) **and** summaries with no decision words: `team_checkin`.
- **Routine title, no summaries**: `key_meeting` / `proceed_without`, medium confidence: "please check".
- **Everything else**: `key_meeting`.

Keyword rules cannot read meaning ("no decisions" vs "decision", a "sync" that is really a sign-off). That is why Gemini decides. See [Rule-based fallback](../architecture/rule-based-fallback.md).

## Large events stay cheap

For a large event where the absent person has no hosting role, the orchestrator skips the AI entirely: engine `rules_policy`. The one exception is when the person is **named** in the title, description or summaries (`[ai] large_event_ai_when_named`), for example "Arjun walks us through the H2 numbers". See `ai_needed` in `agents/orchestrator.py`.

## Related
- [Key people](key-people.md)
- [Guard](../architecture/guard.md)
- [Meeting card](meeting-card.md)
