---
type: Guide
title: Setup
description: Full walkthrough for getting the backend and web app running locally, including optional live Gemini.
resource: README.md
tags: [setup, guide, howto]
timestamp: 2026-10-15T00:00:00Z
---

# Setup

The short command reference lives in [CLAUDE.md](../CLAUDE.md#commands) — this page is the same
ground covered with the *why* and the troubleshooting attached, for whoever's setting this up for
the first time.

## Prerequisites

- **Python 3.13** — the backend pins to it (`py -3.13`). Other 3.x versions may work but aren't
  what's tested.
- **Node.js** (any recent LTS) + npm — for the web app.
- **PowerShell** — the documented commands are PowerShell; all paths below assume Windows.
- **gcloud CLI** — only needed if you turn on live Gemini (see
  [Enabling live Gemini](#enabling-live-gemini) below). Not needed to run the app with the
  rule-based stand-ins, which is the default.

## Backend

Run from `backend/`:

```powershell
py -3.13 -m venv .venv                                          # once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # once
Copy-Item .env.example .env                                     # once
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

What each step does:

- `.venv` — an isolated Python environment so backend dependencies don't collide with anything
  else on the machine.
- `.env` — copied from `.env.example`; holds the environment variables in
  [config/env.md](config/env.md) (`STORE`, `SEED_PATH`, `CORS_ORIGINS`, `NOW`,
  `GOOGLE_CLOUD_PROJECT`). The defaults are enough to run the demo as-is; `NOW` is pinned so the
  seeded absences line up with "today" in the demo.
- `uvicorn --reload` — starts the FastAPI app; `--reload` restarts it on file changes, handy while
  developing.

### Verifying it's up

- `GET http://localhost:8000/health` → `{"ok": true}`.
- `http://localhost:8000/docs` — the live, interactive API reference (every endpoint, try-it in
  the browser). This is always the authoritative source for request/response shapes; see
  [api/index.md](api/index.md) for a curated summary.
- `GET http://localhost:8000/dev/outbox` — starts empty; fills up with simulated "sent" emails as
  you exercise the app (nothing is ever really sent — see
  [architecture/backend.md](architecture/backend.md)).

### Calling protected endpoints

Most endpoints need a simulated sign-in: send header `X-Person-Id: p_priya` (or any id from
[data/seed.md](data/seed.md)). Missing or unknown id → `401`.

### Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q                               # all tests
.\.venv\Scripts\python.exe -m pytest -q tests/test_flow.py::test_name # one test
```

Tests run with `[ai] enabled = false` in `config/settings.toml` — no network calls, the rule-based
stand-ins decide. That's also why you don't need `GOOGLE_CLOUD_PROJECT` or `gcloud` auth just to
develop and test.

## Enabling live Gemini

By default (`[ai] enabled = false` in `backend/config/settings.toml`) the app uses rule-based
stand-ins — see [architecture/recommendation-pipeline.md](architecture/recommendation-pipeline.md).
To see live Gemini recommendations instead:

1. `gcloud auth application-default login` — no API key is used; the app authenticates as you
   (or a service account on Cloud Run) via Application Default Credentials.
2. Set `GOOGLE_CLOUD_PROJECT` in `backend/.env` to a project with Vertex AI enabled.
3. Flip `[ai] enabled = true` in `backend/config/settings.toml` and restart the server.

Demo scripts (`backend/scripts/`, run from `backend/`) are the fastest way to try this without the
full app:

```powershell
.\.venv\Scripts\python.exe scripts\hello_gemini.py --list              # list Gemini models the GCP project can use
.\.venv\Scripts\python.exe scripts\structured_demo.py "Daily Stand-up" # compare the rule-based stand-in vs. live Gemini for one seeded meeting
```

If Gemini is unreachable (no auth, wrong project, network), the app never breaks — it falls back
to the rule-based answer and labels the card `rules_fallback`. See
[architecture/recommendation-pipeline.md](architecture/recommendation-pipeline.md) for the full
retry/fallback flow.

## Web app

Run from `web/`:

```powershell
npm install   # once
npm run dev   # http://localhost:5173
```

`npm run build` / `npm run preview` also exist. No lint/test script is configured for the
frontend. The app expects the backend at `http://localhost:8000` by default (override with
`VITE_API_URL`); if the backend's `CORS_ORIGINS` doesn't include the web app's origin, requests
will fail in the browser console with a CORS error — check `backend/.env`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` on most endpoints | Missing or unrecognized `X-Person-Id` header — see [data/seed.md](data/seed.md) for valid ids. |
| CORS error in the browser console | The web app's origin isn't in the backend's `CORS_ORIGINS` (`backend/.env`). |
| Backend fails at startup reading `settings.toml` | A key is missing — `app/settings.py` fails fast rather than defaulting silently; check the error message against [config/settings.md](config/settings.md). |
| `settings.toml` edits seem ignored | Check `SETTINGS_PATH` isn't pointing elsewhere; restart the server (settings are loaded once at import time, not hot-reloaded). |
| Gemini calls fail or time out | Confirm `gcloud auth application-default login` succeeded and `GOOGLE_CLOUD_PROJECT` has Vertex AI enabled; the app will fall back to rules either way, so this degrades gracefully rather than breaking. |
