---
type: Architecture Component
title: Storage (Store and calendar adapters, Firestore)
description: The persistence interfaces, the in-memory and Firestore implementations, Firestore collections and workspace-scoped document ids, and the per-request read cache.
resource: ../../backend/app/store.py
tags: [storage, firestore, persistence, cache]
sources:
  - resource: ../../backend/app/store.py
  - resource: ../../backend/app/calendar.py
  - resource: ../../backend/app/firestore.py
  - resource: ../../backend/app/seed.py
  - resource: ../../backend/app/config.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Storage

Two adapters hide where data lives:
- **`Store`** (`app/store.py`) holds the app's own data: people, absences, cards, proxy requests, history, tokens, counters.
- **The calendar** (`app/calendar.py`) holds calendar events with their meeting summaries.

`STORE` selects the implementation in `seed.build_service` and `build_company_service`:

| `STORE` | Store | Calendar | Use |
|---|---|---|---|
| `memory` (default) | `InMemoryStore` | `SimCalendar` | Local runs and tests. The demo is loaded from the seed at start |
| `firestore` | `FirestoreStore(client, workspace_id)` | `FirestoreCalendar(client, workspace_id)` | **Required on Cloud Run** (startup fails otherwise) |

## `Store` interface

| Area | Methods |
|---|---|
| People | `people`, `get_person` (Firestore also has `save_person`, `add_person_if_missing`) |
| Absences | `add_absence`, `absences` |
| Cards | `add_item`, `save_item`, `delete_item`, `get_item`, `items` |
| Proxy requests | `add_proxy_request`, `save_proxy_request`, `get_proxy_request`, `proxy_requests` |
| History | `add_history`, `history` |
| Ids | `next_id(prefix)`: in memory `"{prefix}_{n:03d}"`; in Firestore a transactional counter |
| OAuth tokens | `get/save/delete_calendar_token`, `get/save/delete_meet_token` (encrypted strings) |
| Demo status | `get_demo_reset_at`, `save_demo_reset_at` |

## Calendar interface

`get`, `all_events`, `involving(pid)`, `events_in_window(pid, start, end)`, `busy(pid, ignore_event_id)`, `visible_notes(event, viewer)`, `add_event`, `save_event`, `remove_event`, `move_event`, `cancel_event`.

- `involving` covers events where the person is the organizer or an attendee, excluding cancelled ones.
- `visible_notes` is the [privacy filter](privacy-rule.md).

A real Google Calendar integration sits *beside* this adapter, not behind it. Synced events are stored here and written back through `GoogleCalendarIntegration`. See [Google integrations](google-integrations.md).

## Firestore layout

- **Collections**, shared by both areas: `people`, `events` (with their notes), `absences`, `items`, `proxy_requests`, `history`, `metadata` (`counters`, `demo_status`), `calendar_connections`, `meet_connections`.
- **Document id** = `"<workspace>__<id>"`, for example `guest__p_priya` or `company__i_004`. Every document carries a `workspaceId` field.
- **Queries** always filter `workspaceId == <this area>`. The field is stripped when decoding.
- `delete_where(collection, predicate)` deletes in batches of 400 (the Firestore limit is 500). It is used by Reset demo data.
- Firestore permissions are project-wide, so **the backend enforces the area boundary**. Database credentials are never given to the web app.
- The service account needs `roles/datastore.user` in the database's project. `FIRESTORE_PROJECT_ID` can point to another project.

## Per-request read cache

`[store] request_cache = true` (env `STORE_REQUEST_CACHE` overrides it). Implemented by `RequestReads` in `app/firestore.py`:

- `begin_request_reads()` runs at the start of every request (from `choose_area`), in that request's own context.
- **Within one request** each collection is read at most once. A single-document lookup reads the whole collection in one trip, because each area holds only tens of documents per collection.
- The request's own writes go to Firestore first and then update the cached copy (`wrote`, `forget`).
- **Nothing is kept after the request**, so data is never stale.
- Background AI threads run outside any request and read Firestore directly.

This took a page from 80–117 Firestore reads down to about one per collection. Tested in `tests/test_request_cache.py`.

## Related
- [Areas](../concepts/areas.md)
- [Environment variables](../config/environment-variables.md)
- [Reset demo flow](../flows/reset-demo.md)
