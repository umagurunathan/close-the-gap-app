---
type: Configuration
title: Environment variables
description: Every environment variable the backend and the web app read, with defaults, which are secrets, and where each is used.
resource: ../../backend/app/config.py
tags: [configuration, environment, secrets, deployment]
sources:
  - resource: ../../backend/app/config.py
  - resource: ../../backend/app/settings.py
  - resource: ../../backend/app/firebase_auth.py
  - resource: ../../backend/app/google_calendar.py
  - resource: ../../backend/.env.example
  - resource: ../../web/.env.example
  - resource: ../../web/src/firebase.js
  - resource: ../../web/src/api.js
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Environment variables

- **Backend:** locally, copy `backend/.env.example` to `.env`; it is git-ignored and loaded by `python-dotenv`. On Cloud Run these are environment variables, and the **secret** ones come from **Secret Manager**.
- **Web app:** `web/.env.local` or `web/.env.production`, read at build time by Vite.

Tunable numbers are not env vars; they live in [settings.toml](settings-toml.md).

## Backend: core

| Variable | Default | Meaning |
|---|---|---|
| `STORE` | `firestore` | `firestore` (the app always runs on it), or `memory`, which only the tests and CI set. **On Cloud Run (`K_SERVICE` set) anything but `firestore` fails startup** |
| `SEED_PATH` | `seed/seed.json` | The demo seed, relative to `backend/` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `GOOGLE_CLOUD_PROJECT` (or `GCLOUD_PROJECT`) | none | The GCP project for Vertex AI (billing) and Firestore. The AI clients read `GOOGLE_CLOUD_PROJECT` |
| `AI_ENABLED` | from settings (`true`) | Overrides `[ai] enabled` |
| `AI_MODEL` | from settings | Overrides `[ai] model` |
| `STORE_REQUEST_CACHE` | from settings (`true`) | Overrides `[store] request_cache` |
| `SETTINGS_PATH` | `config/settings.toml` | Load a different settings file |
| `K_SERVICE` | set by Cloud Run | Detects Cloud Run: forces Firestore |

## Backend: Firestore and areas

| Variable | Default | Meaning |
|---|---|---|
| `FIRESTORE_DATABASE` | `(default)` | Database id |
| `FIRESTORE_PROJECT_ID` | `GOOGLE_CLOUD_PROJECT` | Only when the database is in another project |
| `FIRESTORE_WORKSPACE_ID` | `company` | Company area name (`[a-z][a-z0-9_]*`) |
| `FIRESTORE_DEMO_WORKSPACE_ID` | `guest` | Demo area name. **Must differ** from the company one, or startup fails |

## Backend: sign-in and directory

| Variable | Secret? | Meaning |
|---|---|---|
| `FIREBASE_AUTH_ENABLED` | no | `true` installs the ID-token middleware |
| `FIREBASE_PROJECT_ID` | no | Required when auth is on; the token audience |
| `COMPANY_DIRECTORY` | **yes** (real names and emails) | JSON list `[{id, name, email, title, department, managerId}]`. Each entry needs `id` and `email` |

## Backend: Google Calendar

| Variable | Secret? | Meaning |
|---|---|---|
| `GOOGLE_CALENDAR_ENABLED` | no | `true` enables hosted Calendar (also needs Firebase auth and Firestore) |
| `GOOGLE_CALENDAR_REDIRECT_URI` | no | `https://<cloud-run-url>/integrations/google-calendar/callback` |
| `GOOGLE_CALENDAR_LOCAL_DEMO_ONLY` | no | Loopback-only local mode (memory store). **Never on Cloud Run** |
| `GOOGLE_OAUTH_CLIENT_ID` | **yes** | OAuth web client |
| `GOOGLE_OAUTH_CLIENT_SECRET` | **yes** | OAuth client secret; also signs the OAuth state |
| `GOOGLE_TOKEN_ENCRYPTION_KEY` | **yes** | Fernet key used to encrypt refresh tokens at rest |
| `WEB_APP_URL` | no | Where OAuth callbacks redirect back to (default `http://localhost:5173`) |

Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

## Backend: reminder job

| Variable | Meaning |
|---|---|
| `RUN_REMINDERS_AUDIENCE` | The exact URL the scheduler's OIDC token is issued for (`https://<cloud-run-url>/jobs/run-reminders`) |
| `REMINDERS_SCHEDULER_SA` | The only service account allowed to call the job |

If either is empty, **the job refuses every call** (it fails closed).

## Backend: legacy (not used by the live app)

`LLM_PROVIDER` (`rules` | `vertex`), `VERTEX_AI_LOCATION` (default `asia-southeast1`) and `GEMINI_MODEL` (default `gemini-3.8-flash`) configure only the older optional proxy ranker inside the rules fallback. See [Rule-based fallback](../architecture/rule-based-fallback.md).

## Web app (`VITE_*`)

| Variable | Meaning |
|---|---|
| `VITE_API_URL` | Backend base URL (default `http://localhost:8000`; on Cloud Run, the service URL) |
| `VITE_FIREBASE_AUTH_ENABLED` | `"true"` turns on Sign in with Google |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Firebase web config. **Public browser configuration, not secrets**; all four are required when auth is on |

## Related
- [Deployment](../operations/deployment.md)
- [Local setup](../operations/local-setup.md)
- [Areas](../concepts/areas.md)
