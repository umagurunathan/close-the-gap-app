---
type: Product Concept
title: Areas (demo and company)
description: One backend serves two isolated data areas, the demo area for guests and the company area for signed-in directory members, chosen per request and never mixed.
resource: ../../backend/app/main.py
tags: [areas, workspace, multi-tenancy, security]
sources:
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/seed.py
  - resource: ../../backend/app/config.py
  - resource: ../../backend/app/store.py
  - resource: ../../backend/README.md
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Areas (demo and company)

One backend serves **two areas**:

- The **demo area** is for every visitor who has not signed in. The visitor acts as one of the sample people from `seed/seed.json`.
- The **company area** is for people who signed in with Google and are in the private company directory. Each person sees only their own work.

Each request is routed to exactly one area, and the two never mix. Comments call these "areas"; config and Firestore call them "workspaces".

## How a request picks its area

1. The Firebase middleware (`app/firebase_auth.py`) runs first. A valid ID token sets `request.state.person_id`. A request with no `Authorization` header passes through as a **guest**. See [Auth and access](../architecture/auth-and-access.md).
2. The global dependency `choose_area` in `app/main.py` sets a context variable to `"company"` if `person_id` is set, and to `"demo"` otherwise.
3. Every endpoint uses `svc`, which is an `_AreaRouter`. Any attribute lookup on it goes to the `Service` of the current request's area, so an endpoint cannot accidentally read the other area.

## The two areas side by side

| | Demo area | Company area |
|---|---|---|
| Built by | `seed.build_service()` | `seed.build_company_service()` |
| Who | Guests sending `X-Person-Id: p_…`, which must be a demo person | Signed-in people whose verified email matches exactly one directory entry |
| People | The 26 seed people | `COMPANY_DIRECTORY` (a JSON list from Secret Manager or the git-ignored `.env`) |
| Meetings | Seed meetings, plus any scheduled in the app | Imported from each person's own Google Calendar, plus any scheduled in the app |
| Clock | `config.now()`: the real clock; `NOW` is honoured only off Cloud Run | `config.real_now()`, always real |
| Firestore name | `FIRESTORE_DEMO_WORKSPACE_ID` (default `guest`) | `FIRESTORE_WORKSPACE_ID` (default `company`) |
| Written by | Only **Reset demo data** | Only real people's own actions, including Calendar sync |
| Demo-only endpoints | `POST /dev/reset-demo`, `POST /dev/simulate-leave-system` | — |
| Company-only features | — | Google Calendar and Meet, `POST /jobs/run-reminders` |

## Safety rails that keep the areas apart

- `create_app` raises at startup if the two workspace ids are equal.
- Workspace ids must match `[a-z][a-z0-9_]*` (`config._area_name`).
- With Firestore, every document id is prefixed `"<workspace>__<id>"` and carries a `workspaceId` field, and every query filters on that field. See [Storage](../architecture/storage.md).
- `reset_demo` raises `PermissionError` if the store's workspace is not the demo workspace.
- **Starting the backend writes nothing to the demo area.** On Firestore, the demo data is loaded only by Reset demo data. The company service does re-save directory people at startup, because the directory is the source of truth.
- Guests cannot pass a company person's id: `me()` checks `X-Person-Id` against the demo store only.
- `GET /dev/outbox` returns only the caller's emails when signed in, and only demo people's emails for guests.

## Where in the code
- `app/main.py`: `_AreaRouter`, `_AREA`, `choose_area`, `me`
- `app/seed.py`: `build_service`, `build_company_service`, `reset_demo`
- `app/config.py`: `firestore_workspace_id`, `demo_workspace_id`, `company_directory`, `now`, `real_now`

## Related
- [Auth and access](../architecture/auth-and-access.md)
- [Storage](../architecture/storage.md)
- [Reset demo flow](../flows/reset-demo.md)
