---
type: Architecture Component
title: Analysis cache and background analysis
description: How Service caches AI answers per meeting and per viewer's visible summaries, answers pages at once with the rules while Gemini works in a thread pool, and avoids hammering the AI after a failure.
resource: ../../backend/app/service.py
tags: [ai, cache, performance, background]
sources:
  - resource: ../../backend/app/service.py
  - resource: ../../backend/config/settings.toml
  - resource: ../../web/src/App.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Analysis cache and background analysis

**Pages never wait for the AI.** `Service._analyze(item, viewer)` returns at once:
- the cached final answer, if there is one;
- otherwise the rules' suggestion labelled `analysing`, while Gemini works in a background thread pool.

The web app polls every `[ai] refresh_while_analysing_seconds` (4 s) while any card says "AI analyzing…", and the card updates by itself.

## Cache key (`_cache_key`)

```
(item.id,
 (title, description, start, organizerId, ((personId, optional), ...)),   # the meeting
 ((docId, modifiedAt), ...),                                               # summaries THIS viewer can open
 (ai.enabled, ai.model, ai.engine))                                        # the AI setup
```

- The AI is asked again **only** when the meeting, the summaries that viewer can see, or the AI setup changes.
- Two viewers who can open the same documents **share one result**.
- **Only final answers are cached** (`_is_final`):
  - with the AI on: engine `gemini_adk`, `gemini` or `rules_policy`;
  - with it off: `rules`.
- A fallback or placeholder is never cached, so the AI is asked again later.
- The cache lives in process memory. It is emptied by **Reset demo data** and lost on restart.

## Decision flow in `_analyze`

1. **Cache hit**: return it.
2. **Answer synchronously** when any of these is true:
   - the AI is off;
   - `allow_ai` is false (card creation);
   - `[ai] background` is false (tests);
   - the meeting is a large event that needs no AI (`ai_needed` is false).
3. **Recent failure**: if the AI failed for this key less than `retry_after_failure_seconds` (300) ago, return the stored fallback without asking again. An outage therefore cannot run up calls on every refresh.
4. **Otherwise**:
   - submit `_analyze_in_background` once per key (`_pending` tracks it);
   - return the rules answer labelled `analysing`;
   - after `analysing_label_max_seconds` (60) it is labelled `rules_fallback` instead, with "the AI is taking longer than usual…". The analysis keeps running and the card updates later.

The pool is a `ThreadPoolExecutor` with `[ai] background_workers` (3) threads (`ai-analysis-*`). More workers give faster pages but more risk of 429s.

## When analysis starts

| Moment | Behaviour |
|---|---|
| Card created | Rules answer only (`analyse_on_creation = false`), then queued in the background from the absent person's view (`analyse_in_background_on_creation = true`). Skipped while the seed replays the past week (`replaying`) |
| Card listed (`_view`) | `_analyze(item, viewer)` for upcoming meetings. A **past** meeting is never analysed again: it shows `aiWhenDecided` or the stored `ai` |
| Server start | `warm_up_on_start`: one tiny Gemini call in a daemon thread, so the first real request does not pay for setting up the connection |
| A decision is made | `apply_action` stores what the decider was shown, read from the cache if present; it never waits for the AI |

## Raising an auto-handled card (`_maybe_raise`)

When a final Gemini answer says `key_meeting` for a card that is still `auto_handled`, the card is moved up to `key_meeting` / `pending_decision` and logged as `ai_raised`. Conditions:
- the answer came from the absent person's view;
- nobody has decided;
- `[ai] ai_may_raise_to_key_meeting` is on.

It is only ever upward.

## Organizer cards

`_meeting_ai` combines the absentees' recommendations with **no extra AI call**:
- the strongest action wins: reschedule > cancel > proxy > proceed_without;
- the reasons are concatenated per person;
- engines are merged: all Gemini gives `gemini`, any still analysing gives `analysing`, otherwise `mixed`.

## Related
- [Recommendation pipeline](recommendation-pipeline.md)
- [AI settings](../config/ai-settings.md)
- [Frontend architecture](frontend-architecture.md) (polling)
