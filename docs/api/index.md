---
type: API Reference
title: API
description: Endpoint summary for the FastAPI backend; the live, authoritative reference is always the running server's /docs.
resource: backend/app/main.py
tags: [api, reference]
timestamp: 2026-10-15T00:00:00Z
---

# API

**The live, interactive, always-accurate reference is `http://localhost:8000/docs`** when the
server is running — every endpoint, every request/response shape, try-it-in-browser. This page is
a map of what exists and why, meant to be read alongside the code, not instead of `/docs`.

All endpoints except `/health`, `/people`, `/metrics` and the `/dev/*` and `/jobs/*` helpers
require a simulated sign-in: header `X-Person-Id: p_priya` (or any id from
[seed/seed.json](../../backend/seed/seed.json) — see [data/seed.md](../data/seed.md)).

## Endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Liveness check. |
| `POST /events` | `X-Person-Id` | Schedule a meeting. If a key person is already out, affected items are created immediately. |
| `POST /events/{id}/attendees` | `X-Person-Id` | Organizer adds an attendee; triggers the same scan for that person only. |
| `GET /people` | none | All people in the directory (raw). |
| `GET /directory` | `X-Person-Id` | Search the directory by email/name/title/team; pass `day` to see who's out that day. |
| `GET /me` | `X-Person-Id` | The signed-in person plus their tab counts. |
| `GET /absences` | `X-Person-Id` | My absences. |
| `POST /absences` | `X-Person-Id` | Report an absence (type is inferred from notice given, not sent by the client). |
| `GET /items?mode=attendee\|organizer\|past` | `X-Person-Id` | The three item views — see [architecture/frontend.md](../architecture/frontend.md#tabs). |
| `POST /items/{id}/action` | `X-Person-Id` | Apply one of the five actions — see [concepts/actions.md](../concepts/actions.md). |
| `GET /items/{id}/note-draft/available` | `X-Person-Id` | Whether an AI-drafted handover note can be offered for this item/proxy. |
| `POST /items/{id}/note-draft` | `X-Person-Id` | Draft a handover note (rule-based today; see `agents/note_drafter.py`). |
| `GET /items/{id}/proxy-candidates` | `X-Person-Id` | Ranked proxy candidates for this item. |
| `GET /items/{id}/proposed-time` | `X-Person-Id` | What `scheduling.find_slot` would propose, without applying it. |
| `POST /items/{id}/reschedule` | `X-Person-Id` | Shortcut for `action=reschedule`. |
| `GET /proxy-requests?past=` | `X-Person-Id` | Proxy requests addressed to me. |
| `POST /proxy-requests/{id}/respond` | `X-Person-Id` | Accept or decline a proxy request. |
| `GET /history` | `X-Person-Id` | My activity log (last `visibility.history_days` days). |
| `GET /metrics` | none | Aggregate demo metrics (meetings resolved, avg lead time, minutes saved). |
| `POST /dev/simulate-leave-system` | none | Dev helper: create an absence as if it came from an external leave system. |
| `GET /dev/outbox` | none | Every simulated "sent" email — nothing is really sent. |
| `POST /jobs/run-reminders` | none | Intended to be called by Cloud Scheduler on an interval; reminds silent proxies and alerts organizers. Never acts on its own. |

See [architecture/backend.md](../architecture/backend.md#appmainpy--the-api) for how these are
wired (the `me` dependency, the `guard` error-mapping helper).
