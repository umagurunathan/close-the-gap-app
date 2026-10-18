---
type: Runbook
title: Known quirks and code/doc drift
description: Small inconsistencies and non-obvious behaviours found while reading the whole codebase for this knowledge bundle, so a human or agent is not surprised by them.
resource: ../../backend/app/service.py
tags: [quirks, maintenance, drift, gotchas]
sources:
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/config.py
  - resource: ../../backend/agents/orchestrator.py
  - resource: ../../backend/agents/fallback/rules_recommender.py
  - resource: ../../web/.env.example
  - resource: ../../web/src/App.jsx
  - resource: ../../web/src/storage.js
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Known quirks and code/doc drift

These were found while reading the whole codebase at commit `0a944b6`. None of them breaks the product. They are listed so a reader or an agent knows what is intentional and what is leftover.

## Behaviour worth knowing

| Quirk | Where |
|---|---|
| **Day boundaries are UTC everywhere**: absence day matching, the "sudden" notice (start of day at 00:00 UTC), and the slot search. The UI shows IST | `absence_type`, `events_in_window`, `find_slot` |
| The `mine` query parameter on `GET /absences`, `/proxy-requests` and `/history` is accepted but ignored; results are always the caller's | `app/main.py` |
| Some endpoints need no identity (`/people`, `/people/active`, `/metrics`, `/metrics/projection`, `/settings/public`), but still read the caller's area | `app/main.py` |
| List endpoints (`/items`, `/organizer/meetings`, `/history`, `/proxy-requests` GET, `/absences` GET, `/people/active`, `/metrics`) are not wrapped in `guard()`, so an unexpected `LookupError` there would be a 500 | `app/main.py` |
| A decline emails the absent person and `event.organizerId`, not `organizer_decider` (the organizer's manager on a sudden absence where the organizer is the one out) | `respond_proxy` |
| `meeting_scheduled` history entries use itemId `"-"`, so they appear only in the actor's own history | `schedule_meeting` |
| `RESOLVED` is defined in `service.py` but not used | `service.py` |
| The in-memory store's `next_id` restarts per process; Firestore uses a transactional counter | `store.py` |
| `.env.example` sets `NOW=2026-10-11T09:00:00Z`, so a local run copied from it is **not** on the real clock, unlike Cloud Run | `backend/.env.example`, `config.now` |

## Drift between comments and code

| Drift | Detail |
|---|---|
| `VITE_DEMO_API_URL` | In `web/.env.example`, but no code reads it; only `VITE_API_URL` is used |
| The orchestrator's comment "the app runs without the Google library when AI is off" | Not fully true: `agents/fallback/rules_recommender.py` imports `vertex_proxy_ranker`, which imports `google.genai` at module level |
| The legacy ranker's defaults | `GEMINI_MODEL=gemini-3.8-flash` and `VERTEX_AI_LOCATION=asia-southeast1` differ from `[ai] model` / `location`. It is only used with `LLM_PROVIDER=vertex` |
| `recommender_ai.py` docstring | Says "same signature as the rule-based `recommend` in recommender.py"; the file is now `agents/fallback/rules_recommender.py` |
| The tool name `get_meeting` | Appears in a `models.py` comment and in test fakes, but is not one of the agent's tools (`read_summaries`, `list_proxy_candidates`, `check_if_out`) |
| Guard docstring order | Rule 9 is listed before 8, and the code runs rule 6 last. The numbers are labels, not the execution order |
| Dates in comments | `guard.py` says "found 2026-10-15" while tests say "found 2026-11-12"; the tests were shifted with the seed dates |
| `storage.js` / `styles.css` comments | Mention remembering whether the guide was opened, but nothing stores that, and the guide button is always highlighted |
| `AuthGate.jsx` comment | Says Sign in with Google is "in the Demo controls"; it is in the header |
| UI spelling | The README says "AI analysing…" and "Demo data last reset"; the UI shows "AI analyzing…" and "Last reset: …" |
| Unused helpers | `noticeAction` (the MessageBar action) is always null; `plural` is imported but unused in `App.jsx` |
| `CLAUDE.md` (git-ignored) | Described an older version: refreshed alongside this bundle |

## Related
- [Limits and future scope](../overview/limits-and-future-scope.md)
- [Backend layers](../architecture/backend-layers.md)
