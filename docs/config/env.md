---
type: Config Reference
title: Environment variables
description: Everything read from .env / the process environment, via app/config.py.
resource: backend/app/config.py
tags: [config, env, reference]
timestamp: 2026-10-15T00:00:00Z
---

# Environment (`.env`)

Read by [`app/config.py`](../../backend/app/config.py) so the same code runs locally and on Cloud
Run. Copy `backend/.env.example` to `backend/.env` to get started.

| Variable | Default | Meaning |
|---|---|---|
| `STORE` | `"memory"` | Which `Store` implementation to use. Only `InMemoryStore` exists today; `firestore` is the planned value once a `FirestoreStore` is built. See [architecture/backend.md](../architecture/backend.md#adapters-swappable-by-construction-not-by-branching). |
| `SEED_PATH` | `"seed/seed.json"` | Where the demo world is loaded from. See [data/seed.md](../data/seed.md). |
| `CORS_ORIGINS` | `"http://localhost:5173"` | Comma-separated list of allowed origins for the web app. |
| `NOW` | unset (real wall-clock time) | ISO datetime that fixes "now" for deterministic demos/tests, e.g. `2026-10-11T09:00:00Z`. |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project used by `agents/recommender_ai.py` to talk to Vertex AI (no API key — uses `gcloud auth application-default login` credentials). Only required when `[ai] enabled = true`. |
| `SETTINGS_PATH` | unset (uses `config/settings.toml`) | Overrides which settings file `app/settings.py` loads — not a `.env`-documented var itself, but same mechanism. |

Tunable numbers and word lists (reminders, urgency, reschedule search, metrics, AI
model/thresholds) live in `config/settings.toml`, not here — see
[config/settings.md](settings.md).
