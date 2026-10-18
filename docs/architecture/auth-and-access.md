---
type: Architecture Component
title: Authentication, identity and rate limits
description: How a request becomes a person (Firebase ID token mapped to one directory entry, or a demo guest via X-Person-Id), how the reminder job is authenticated with OIDC, CORS, and the per-visitor rate limits.
resource: ../../backend/app/firebase_auth.py
tags: [auth, firebase, oidc, security, rate-limits]
sources:
  - resource: ../../backend/app/firebase_auth.py
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/limits.py
  - resource: ../../backend/config/settings.toml
  - resource: ../../web/src/api.js
  - resource: ../../web/src/AuthGate.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Authentication, identity and rate limits

There are two kinds of caller:

- **Signed-in people** send a Firebase ID token. The token is verified on every request and mapped to exactly one directory person. They work in the **company area**, only as themselves.
- **Guests** send no token. They pick a demo person with the `X-Person-Id` header and work in the **demo area**.

## Firebase sign-in (`app/firebase_auth.py`)

The middleware is installed only when `FIREBASE_AUTH_ENABLED=true`, and then `FIREBASE_PROJECT_ID` is required. For each request:

1. `OPTIONS` requests and `PUBLIC_PATHS` pass straight through. `PUBLIC_PATHS` are `/`, `/health`, the Calendar OAuth callback, and `/jobs/run-reminders`.
2. **No `Authorization` header**: the request continues as a guest.
3. A header that is not `Bearer`: 401.
4. `verify_firebase_token(token, audience=FIREBASE_PROJECT_ID)` fails: 401 "Your sign-in expired".
5. Email missing or not verified: 403.
6. The email (case-insensitive) must match **exactly one non-group person in the company directory**. Otherwise: 403 with `code: "not_in_directory"`. The web app then signs the person out and they keep using the demo.
7. An `X-Person-Id` header that differs from the matched person: 403.
8. Success: `request.state.person_id` and `email` are set, and `choose_area` selects the company area.

## Guests (`me()` in `app/main.py`)

- With no verified person, `X-Person-Id` must name a person in the **demo** store. Otherwise: 401 "Please choose a demo person…".
- A company person's id is therefore refused for guests.
- There is no credential for guests: anyone may act as any demo person. That is intended, since it is sample data.

## Web side

- `web/src/firebase.js` uses the Google provider with `prompt: select_account` and a popup.
- `AuthGate.jsx` listens to `onAuthStateChanged` and gives `api.js` a token provider, `user.getIdToken()`, which refreshes itself.
- `api.js` sends `Authorization: Bearer <token>` when signed in. It sends `X-Person-Id` **only when there is no token**.
- The Firebase web config (`VITE_FIREBASE_*`) is public browser configuration, not a secret.

## Reminder job (OIDC, `require_scheduler`)

`POST /jobs/run-reminders` is public on the network but checks a **Google-signed OIDC token** itself:
1. Both `RUN_REMINDERS_AUDIENCE` and `REMINDERS_SCHEDULER_SA` must be set. Otherwise every call gets 403 (fail closed).
2. A Bearer token is required (401).
3. `id_token.verify_oauth2_token(..., audience=RUN_REMINDERS_AUDIENCE)` must pass. A bad token, or failing to reach Google's keys, gives 401.
4. `email` must equal the scheduler service account (case-insensitive) and `email_verified` must be true (403).

It runs `company_svc.run_reminders()` only. No shared secret is stored anywhere. Tested in `tests/test_run_reminders_auth.py` (12 tests). Setup: [Reminder job](../operations/reminder-job.md).

## Other access helpers

| Helper | Rule |
|---|---|
| `real_people_only` | 403 for guests on Calendar connect and sync |
| `require_calendar_request` | Passes when hosted Calendar is enabled; otherwise only loopback clients (the local demo mode) |
| CORS | `CORS_ORIGINS` (default `http://localhost:5173`), all methods and headers |

## Rate limits

`app/limits.py`, settings `[limits]`:

| Action | Limit |
|---|---|
| "Draft with AI" (`POST /items/{id}/note-draft`) | `draft_with_ai` = 10 per `window_minutes` = 10 |
| "Reset demo data" (`POST /dev/reset-demo`) | `reset_demo` = 2 per 10 minutes |

- `RateLimiter.hit` is a sliding window. Over the limit it returns the whole minutes to wait (at least 1), and the endpoint responds **429** with a polite message.
- A refused try is not counted, so waiting is always enough. A limit of `0` means no limit.
- The key is `visitor_key`: `person:<id>` when signed in, otherwise `guest:<first X-Forwarded-For address or client host>`. **Switching demo persons does not reset a guest's count.**
- Counts are in memory, per instance. That is acceptable with one instance.

## Related
- [Areas](../concepts/areas.md)
- [Permissions](../concepts/permissions.md)
- [Environment variables](../config/environment-variables.md)
