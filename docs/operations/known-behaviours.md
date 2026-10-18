---
type: Runbook
title: Known behaviours
description: Small, non-obvious behaviours and leftover inconsistencies in the code, so a human or agent is not surprised by them.
resource: ../../backend/app/service.py
tags: [behaviours, maintenance, gotchas]
sources:
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/config.py
  - resource: ../../backend/agents/orchestrator.py
  - resource: ../../backend/agents/fallback/rules_recommender.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Known behaviours

None of these breaks the product. They are listed so a reader or an agent knows what is intentional and what is leftover.

## Behaviour worth knowing

| Quirk | Where |
|---|---|
| **Day boundaries are UTC everywhere**: absence day matching, the "sudden" notice (start of day at 00:00 UTC), and the slot search. The UI shows IST | `absence_type`, `events_in_window`, `find_slot` |
| The `mine` query parameter on `GET /absences`, `/proxy-requests` and `/history` is accepted but ignored; results are always the caller's | `app/main.py` |
| Some endpoints need no identity (`/people`, `/people/active`, `/metrics`, `/metrics/projection`, `/settings/public`), but still read the caller's area | `app/main.py` |
| List endpoints (`/items`, `/organizer/meetings`, `/history`, `/proxy-requests` GET, `/absences` GET, `/people/active`, `/metrics`) are not wrapped in `guard()`, so an unexpected `LookupError` there would be a 500 | `app/main.py` |
| `meeting_scheduled` history entries use itemId `"-"`, so they appear only in the actor's own history | `schedule_meeting` |
| `RESOLVED` is defined in `service.py` but not used | `service.py` |
| The in-memory store's `next_id` restarts per process; Firestore uses a transactional counter | `store.py` |

## Drift between comments and code

| Drift | Detail |
|---|---|
| The legacy ranker's defaults | `GEMINI_MODEL=gemini-3.8-flash` and `VERTEX_AI_LOCATION=asia-southeast1` differ from `[ai] model` / `location`. It is only used with `LLM_PROVIDER=vertex` |
| The tool name `get_meeting` | Appears in a `models.py` comment and in test fakes, but is not one of the agent's tools (`read_summaries`, `list_proxy_candidates`, `check_if_out`) |
| Guard docstring order | Rule 9 is listed before 8, and the code runs rule 6 last. The numbers are labels, not the execution order |
| Dates in comments | `guard.py` says "found 2026-10-15" while tests say "found 2026-11-12"; the tests were shifted with the seed dates |
| Unused helpers | `noticeAction` (the MessageBar action) is always null; `plural` is imported but unused in `App.jsx` |
| `run_reminders` docstring | Says "Cloud Scheduler later"; the job already runs hourly on Cloud Scheduler |

## Related
- [Limits and future scope](../overview/limits-and-future-scope.md)
- [Backend layers](../architecture/backend-layers.md)
