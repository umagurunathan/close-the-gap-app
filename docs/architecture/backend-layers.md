---
type: Architecture Component
title: Backend layers and module map
description: How the FastAPI backend is layered (thin endpoints in main.py, all logic in Service, AI in agents/, adapters for calendar and storage) and what every module is for.
resource: ../../backend/app/main.py
tags: [backend, architecture, fastapi, layering]
sources:
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/README.md
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Backend layers and module map

```
HTTP ──> app/main.py ──> app/service.py (Service) ──┬─> agents/      (recommendation, guard, drafting)
         thin endpoints   all business logic         ├─> app/calendar.py  (calendar adapter)
         auth, areas,     callable without a server  ├─> app/store.py     (persistence adapter)
         error mapping                               ├─> app/scheduling.py, app/roles.py (plain rules)
                                                     └─> app/notify.py    (email outbox)
```

- **`app/main.py` is thin.** It handles routing, picks the area, resolves identity (`me`), applies rate limits, checks the Calendar request, and maps errors. It also orchestrates the Google Calendar write that must happen *before* a local change, as in `POST /events`.
- **`app/service.py` holds every rule** (`Service`). It can be tested without a web server; most of the 150 tests call it directly.
- **Adapters** (`SimCalendar` / `FirestoreCalendar`, `InMemoryStore` / `FirestoreStore`) share one interface each, so the storage backend is a config switch (`STORE`).
- **`agents/`** is the only place that talks to Gemini. Its one entry point is `agents/orchestrator.analyze`.

## Error mapping (`guard()` in `main.py`)

| Exception raised in `Service` | HTTP |
|---|---|
| `LookupError` | 404 |
| `PermissionError` | 403 |
| `ValueError` | 400 |
| `MeetIntegrationError`, `CalendarIntegrationError` | 503 |

Messages are written in plain language for the end user. The web app shows `detail` as-is. Some list endpoints (`/items`, `/organizer/meetings`, `/history`, `/metrics`, …) are not wrapped in `guard()`.

## Module map

| Module | Purpose |
|---|---|
| `app/main.py` | `create_app()`, the 44 endpoints, `_AreaRouter`, `me`, `require_scheduler`, `limit`, `real_people_only`, `require_calendar_request` |
| `app/service.py` | `Service`: absences and scans, scheduling, Calendar sync, listing and views, actions, proxy flow, notes and drafts, reminders, history, metrics, projection, analysis cache |
| `app/models.py` | Pydantic shapes. Field names are **camelCase on purpose**: the same names as the API and the web app. See [Data models](../api/data-models.md) |
| `app/roles.py` | Who matters in a meeting. See [Key people](../concepts/key-people.md) |
| `app/scheduling.py` | `find_slot`, the reschedule search. See [Reschedule search](reschedule-search.md) |
| `app/calendar.py` | `SimCalendar`, `FirestoreCalendar`, `visible_notes` (the privacy filter) |
| `app/store.py` | `Store` interface, `InMemoryStore`, `FirestoreStore`. See [Storage](storage.md) |
| `app/firestore.py` | Firestore client, model encoding, per-request read cache |
| `app/firebase_auth.py` | ID-token middleware and the match to one directory person |
| `app/google_calendar.py` | Calendar OAuth, encrypted tokens, import and write-back |
| `app/limits.py` | `RateLimiter`, `visitor_key` |
| `app/notify.py` | `OUTBOX`, `send_email` (in memory, not sent) |
| `app/seed.py` | `build_service`, `build_company_service`, `reset_demo`, past-week replay |
| `app/settings.py` | Loads `config/settings.toml` (`SETTINGS_PATH`); env overrides `AI_ENABLED`, `AI_MODEL`, `STORE_REQUEST_CACHE` |
| `app/config.py` | Environment-driven config: store, areas, directory, Firebase, CORS, clock, scheduler. See [Environment variables](../config/environment-variables.md) |
| `agents/orchestrator.py` | `analyze()`, `ai_needed()`, `_with_retries()` |
| `agents/adk_advisor.py` | The ADK meeting advisor and its three tools |
| `agents/recommender_ai.py` | The single-call Gemini recommender; `Recommendation` schema; `candidates_for`; `warm_up` |
| `agents/guard.py` | Layer C checks |
| `agents/untrusted.py` | Prompt-injection markers and detection |
| `agents/note_drafter.py` | The Gemini handover brief |
| `agents/fallback/` | Rules recommender, proxy ordering, simple note (fallback only) |
| `agents/vertex_proxy_ranker.py` | Legacy optional ranker inside the rules fallback (`LLM_PROVIDER=vertex`); not used by the live app |

## Startup sequence (`create_app`)

1. Refuse to start if the demo and company workspace ids are equal.
2. Build `demo_svc` (`build_service`) and `company_svc` (`build_company_service`). Tests pass one service, used for both.
3. If the AI is on and `[ai] warm_up_on_start` is set, start a daemon thread that makes one tiny Gemini call.
4. Bind the Calendar integration to the company area only.
5. Install the Firebase middleware and CORS (`CORS_ORIGINS`).

`config.store_kind()` defaults to Firestore, and on Cloud Run it raises for any other value, so the last good revision keeps serving instead of one that would lose data.

## Related
- [Endpoints](../api/endpoints.md)
- [System overview](system-overview.md)
- [Recommendation pipeline](recommendation-pipeline.md)
