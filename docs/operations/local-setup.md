---
type: Runbook
title: Run it locally
description: Prerequisites and the two-terminal setup (FastAPI backend on :8000, Vite web app on :5173), enabling live Gemini, verifying it works, and common problems.
resource: ../../README.md
tags: [setup, local, runbook, developer]
sources:
  - resource: ../../README.md
  - resource: ../../backend/README.md
  - resource: ../../backend/.env.example
  - resource: ../../web/.env.example
  - resource: ../../web/vite.config.js
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Run it locally

## Prerequisites

- **Python 3.13**. On Windows, use the `py` launcher.
- **Node.js 20** (the version CI uses) with npm.
- A Google Cloud project with the **Vertex AI API** (for Gemini) and a **Firestore** database (for the data), and the **gcloud CLI**. The app always runs on Firestore.

## 1. Backend (terminal 1, from `backend/`)

```powershell
py -3.13 -m venv .venv                                          # once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # once
Copy-Item .env.example .env                                     # once
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>. Health: <http://localhost:8000/health>, which returns `{"ok": true, "store": "FirestoreStore"}`.
- With the defaults from `.env.example`, `STORE=firestore`: the data lives in Firestore, and starting the backend writes nothing. Press **Reset demo data** once to load the sample data into the demo area. The clock is always the real clock, as on Cloud Run: there is no setting to fix it.
- **Simulated sign-in** for API calls: send `X-Person-Id: p_priya`, or any demo id from [Seed world](../data/seed-world.md).
- Emails are not sent. Read them at `GET /dev/outbox`.

### Live Gemini

Gemini is **always on** (`[ai] enabled = true`). Both Gemini and Firestore need:
1. Your project id in `.env` as `GOOGLE_CLOUD_PROJECT`. If the Firestore database is in another project, also `FIRESTORE_PROJECT_ID`.
2. One sign-in with `gcloud auth application-default login`, as an account that can use Vertex AI and Firestore (`roles/datastore.user`). There is no API key.

Without these the app cannot store data or reach Gemini. Only the automated tests run without Google Cloud: they use an in-memory store and the rules or fakes, and set that up themselves.

## 2. Web app (terminal 2, from `web/`)

```powershell
npm install      # once
npm run dev      # http://localhost:5173
```

- Open **`http://localhost:5173`, not `127.0.0.1`**. The default `CORS_ORIGINS` and the OAuth redirects name `localhost`.
- `VITE_API_URL` defaults to `http://localhost:8000`. Sign-in is off unless `VITE_FIREBASE_AUTH_ENABLED=true` with the Firebase web config in `web/.env.local`.
- Deep link: `?as=p_sam&tab=organizer`.

## Optional local features

| Feature | How |
|---|---|
| Sign in with Google | `FIREBASE_AUTH_ENABLED=true`, `FIREBASE_PROJECT_ID`, `COMPANY_DIRECTORY` in `.env`, and the `VITE_FIREBASE_*` values in `web/.env.local` |
| Google Calendar | `GOOGLE_CALENDAR_ENABLED=true` with Firebase sign-in, a redirect URI, and the OAuth client and Fernet key (an in-memory loopback mode, `GOOGLE_CALENDAR_LOCAL_DEMO_ONLY`, exists for isolated tests only) |
| Reminder job | `RUN_REMINDERS_AUDIENCE=http://localhost:8000/jobs/run-reminders` and `REMINDERS_SCHEDULER_SA`. See [Reminder job](reminder-job.md) |

All variables are listed in [Environment variables](../config/environment-variables.md).

## Verify

1. Open the web app. You are Priya, and the banner says she is out 17–19 Nov.
2. Attendee Mode lists her affected meetings. Stand-ups are under **No action needed**.
3. Open **Q4 Budget Review**. With Gemini working, the source pill says "Gemini · ADK agent" after a few seconds.
4. Run the tests (see [Testing and CI](testing-and-ci.md)). All 150 should pass.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Web app says "We can't reach the server" | The backend is not running on :8000, or `VITE_API_URL` is wrong |
| CORS errors in the browser console | Opened on `127.0.0.1`, or the origin is not in `CORS_ORIGINS` |
| 401 "Please choose a demo person…" from the API | Send `X-Person-Id` with a demo id |
| Cards stay "AI analyzing…" and then "AI unavailable" | No `GOOGLE_CLOUD_PROJECT` or ADC credentials, or the Vertex AI API is not enabled |
| Startup fails: "STORE must be 'firestore' on Cloud Run" | `K_SERVICE` is set in your shell; it is a Cloud Run variable, so unset it |
| Startup fails: areas must differ | `FIRESTORE_DEMO_WORKSPACE_ID` equals `FIRESTORE_WORKSPACE_ID` |
| A setting seems ignored | Edit `config/settings.toml`, then restart (`--reload` only watches Python files) |

## Related
- [Deployment](deployment.md)
- [Environment variables](../config/environment-variables.md)
