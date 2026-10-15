---
type: Component
title: Backend layering
description: How FastAPI, Service, the agents, and the adapters fit together in backend/.
resource: backend/app/main.py
tags: [architecture, backend, fastapi]
timestamp: 2026-10-15T00:00:00Z
---

# Backend layering

```
app/main.py  (HTTP endpoints, thin)
     │
     ▼
app/service.py  (Service: all business logic, callable without a web server)
     │
     ├──▶ agents/orchestrator.py  (recommendation — see [recommendation pipeline](recommendation-pipeline.md))
     ├──▶ app/calendar.py  (SimCalendar — calendar adapter)
     ├──▶ app/store.py  (Store / InMemoryStore — persistence adapter)
     ├──▶ app/scheduling.py  (reschedule search; plain code, no AI)
     └──▶ app/notify.py  (in-memory email outbox)
```

## `app/main.py` — the API

One `create_app()` factory ([backend/app/main.py](../../backend/app/main.py)) wires up all routes.
Two small local helpers carry the whole surface:

- `me()` — a FastAPI dependency that reads the `X-Person-Id` header and 401s if it's missing or
  unknown. This is the entire "auth" model (simulated sign-in, see
  [data/seed.md](../data/seed.md)).
- `guard(fn)` — catches `LookupError` / `PermissionError` / `ValueError` from the service layer and
  turns them into 404 / 403 / 400 responses. Every mutating endpoint is a one-line
  `return guard(lambda: svc.…)`.

Every endpoint is also documented live and interactively at `/docs` on the running server — that's
the authoritative reference; see [api/index.md](../api/index.md) for a summary table.

## `app/service.py` — `Service`

All business logic lives in one `Service` class so it's testable without a web server. It owns:

- an `_analysis_cache` keyed on `(item id, meeting fingerprint, visible-notes fingerprint, ai
  config)` — see [recommendation pipeline](recommendation-pipeline.md#caching).
- the item lifecycle: `create_absence` / `schedule_meeting` → `_scan` / `_scan_event` →
  `_create_item` → `apply_action`. See [item lifecycle](item-lifecycle.md).
- who may act on an item (`_organizer_side`, `organizer_decider`): normally the organizer, or the
  absent person's manager when the organizer is the one who's out.
- notifications: every state change that matters to someone emits an email via `notify.send_email`
  (collected in an in-memory outbox, visible at `GET /dev/outbox`, nothing is really sent).

## Adapters: swappable by construction, not by branching

Two parts of the backend are deliberately written as a narrow interface with exactly one
implementation today, so a second implementation can be dropped in without touching callers:

| Interface | File | Current implementation | Future implementation |
|---|---|---|---|
| `Store` | [backend/app/store.py](../../backend/app/store.py) | `InMemoryStore` (resets on restart) | `FirestoreStore`, selected via `STORE=firestore` |
| calendar adapter | [backend/app/calendar.py](../../backend/app/calendar.py) | `SimCalendar` (seeded in-memory events + notes) | a real Google Calendar integration with the same methods (`get`, `involving`, `visible_notes`, `add_event`, `move_event`, `cancel_event`) |

Nothing in `Service` or the agents knows which implementation it's talking to.

## Supporting modules

- [`app/settings.py`](../../backend/app/settings.py) — loads `config/settings.toml` into
  `settings.<section>.<key>`; a missing key fails fast at startup. See
  [config/settings.md](../config/settings.md).
- [`app/config.py`](../../backend/app/config.py) — environment-driven config from `.env`:
  `STORE`, `SEED_PATH`, `CORS_ORIGINS`, a fixable `NOW`, `GOOGLE_CLOUD_PROJECT`. See
  [config/env.md](../config/env.md).
- [`app/scheduling.py`](../../backend/app/scheduling.py) — the reschedule search: plain
  deterministic code, no AI. Tries the same time of day first (±1h), then widens (±2h), skipping
  weekends, until every key person is free and not on leave.
- [`app/seed.py`](../../backend/app/seed.py) — builds the whole demo world from
  `seed/seed.json` at startup. See [data/seed.md](../data/seed.md).
- [`app/models.py`](../../backend/app/models.py) — every pydantic data shape. Field names are
  camelCase on purpose: the API and the web app share the exact same field names, so there's no
  translation layer at the boundary.
