---
type: Runbook
title: Testing and CI
description: How to run the 142 offline backend tests, how they isolate themselves (memory store, AI off or faked, fixed clock), what each test file covers, and the GitHub Actions workflow.
resource: ../../backend/tests/test_flow.py
tags: [testing, pytest, ci, github-actions]
sources:
  - resource: ../../backend/tests/conftest.py
  - resource: ../../backend/tests/test_flow.py
  - resource: ../../backend/tests/test_run_reminders_auth.py
  - resource: ../../backend/tests/test_request_cache.py
  - resource: ../../backend/tests/test_firebase_auth.py
  - resource: ../../backend/tests/test_firestore_workspace.py
  - resource: ../../.github/workflows/ci.yml
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Testing and CI

## Run the tests (from `backend/`)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # once: adds pytest
.\.venv\Scripts\python.exe -m pytest -q                             # all 142 tests
.\.venv\Scripts\python.exe -m pytest -q tests/test_flow.py::test_reschedule_keeps_time_of_day_and_avoids_leave   # one test
```

There are no frontend tests or lint scripts. CI only builds the web app.

## How the tests isolate themselves

- `tests/conftest.py` runs before every test file and sets:
  - `STORE=memory`, even if your `.env` points at Firestore, so a test can never write to a real database;
  - `AI_ENABLED=false`;
  - `NOW=2026-11-08T09:00:00Z` (Sunday 8 Nov 2026);
  - and it removes `FIRESTORE_PROJECT_ID` and `FIRESTORE_DATABASE`.
- An autouse fixture in `test_flow.py` sets `[ai] engine = "genai"` and `background = False`, so every test waits for its (fake) AI answer.
- **AI tests use fakes, never Google:**
  - `_FakeGemini` returns a ready answer for the single call;
  - `_adk_on` swaps the ADK `_run_sync` for a fake loop that reports which tools it "used".
- A **fake Firestore** checks the request read cache and the workspace scoping.
- No cloud account is needed.

## What is covered

| File | Tests | Themes |
|---|---|---|
| `test_flow.py` | 111 | Cards and grouping; proxy flow (accept, decline, replace, outside proxy, reminders); permissions; sudden and planned absences and alerts; scheduling while someone is out; privacy per viewer; reschedule and cancel (Google first, picked times, no slot); Calendar and Meet OAuth and sync; demo reset and areas; Cloud Run safety (Firestore required, real clock); rate limits; the legacy Vertex ranker; single-call prompt contents; every guard rule; retries, caching and background analysis; large events and optional invitees; the AI raising a card; ADK tools and checks; the handover brief; **prompt injection** (attacks flagged, normal agendas not flagged, no seed text flagged); metrics and projection |
| `test_run_reminders_auth.py` | 12 | OIDC on `/jobs/run-reminders`: missing, invalid or wrong tokens, an unverified email, Google unreachable, fails closed when unconfigured, company area only, passes the Firebase middleware |
| `test_request_cache.py` | 7 | Each collection read once per request; a request sees its own writes; new requests see others' changes; copies, not shared objects; deletes; the two areas never share reads; switching the cache off |
| `test_firebase_auth.py` | 7 | Verified email maps to exactly one directory person; cannot select another person; unmapped or unverified accounts are rejected; no token means a demo guest; CORS on auth errors; signed-in people cannot reset the demo and see only their own emails; the areas never mix |
| `test_firestore_workspace.py` | 5 | Workspace-scoped document ids (`guest__p_priya`), the `workspaceId` filter, calendar scoping, guest email updates, workspace id validation |

Notable guard tests:
- `seed_meetings_stay_upcoming_through_the_evaluation_and_kiran_stays_sudden` keeps the seed dates valid on the real clock;
- `settings_file_loads_and_drives_the_app` checks the settings file.

## CI (`.github/workflows/ci.yml`)

It runs on every pull request and on pushes to `main`, with permissions `contents: read`.

| Job | Steps |
|---|---|
| `backend` | Python 3.13 (pip cache) → `pip install -r requirements-dev.txt` → `python -m pytest -q` with `AI_ENABLED=false` |
| `web` | Node 20 (npm cache) → `npm ci` → `npm run build` |

## Adding a test

- Most tests build a fresh demo with `build_service()` (the `svc` fixture) and call `Service` methods directly.
- Use `TestClient(create_app(svc))` for HTTP-level checks.
- Never call Google: fake the client, as the existing AI tests do.
- If you move the seed dates, move the dates in the tests by the same number of whole weeks.

## Related
- [Local setup](local-setup.md)
- [Guard](../architecture/guard.md)
