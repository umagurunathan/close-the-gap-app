# Close the Gap — backend

Python 3.13 · FastAPI. Runs locally; Cloud Run ready (a Dockerfile, and settings come from environment variables).

## Run it
```powershell
cd backend
py -3.13 -m venv .venv                                          # once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # once
Copy-Item .env.example .env                                     # once
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
- Live API docs (every endpoint and its shapes; you can try them in the browser): http://localhost:8000/docs
- Simulated sign-in: send the header `X-Person-Id: p_priya` (the people are in `seed/seed.json`).
- Emails are not sent yet; the ones the app "sends" are listed at `GET /dev/outbox`.
- **Gemini** is off by default (`[ai] enabled = false` in `config/settings.toml`), so the app and the tests run without a cloud account. To switch it on: set `GOOGLE_CLOUD_PROJECT` in `.env`, run `gcloud auth application-default login` once, and start with `$env:AI_ENABLED="true"`. There is no API key; Vertex AI uses your Google sign-in (on Cloud Run, the service account).

## Test it
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Where things are
| Path | What |
|---|---|
| `app/main.py` | The endpoints |
| `app/service.py` | The logic: scan an absence, check a new meeting, actions, proxy flow, reminders, metrics |
| `app/models.py` | The data shapes |
| `app/scheduling.py` | Reschedule search: plain code, same time of day ±1h then ±2h |
| `app/roles.py` | Who is a key person: required invitees, large events (a list, or more than 15 required people), hosting roles, optional invitees |
| `app/settings.py` | Reads `config/settings.toml`; `AI_ENABLED` in the environment overrides `[ai] enabled` |
| `app/calendar.py` | Simulated calendar. A real calendar can be added behind the same methods |
| `app/store.py` | Storage interface. In-memory now; Firestore can be added behind it |
| `app/notify.py` | Email outbox (stand-in for real email) |
| `agents/orchestrator.py` | Decides how each card is analysed: rules when the AI is off or for a large event; otherwise the ADK agent, then (if it fails) one Gemini call with retries, then the rules; the checks run on any AI answer |
| `agents/adk_advisor.py` | The meeting advisor, an ADK agent with four tools bound to one meeting and one viewer (`get_meeting`, `read_summaries`, `list_proxy_candidates`, `check_if_out`) |
| `agents/recommender_ai.py` | The single-call Gemini recommender (the agent's fallback, and `[ai] engine = "genai"`): builds the prompt (only summaries the viewer can open, candidates who are not out that day), asks for a structured answer |
| `agents/guard.py` | Plain-code checks on every AI answer (proxy must be a valid candidate, confidence caps, auto-handling only at high confidence) |
| `agents/note_drafter.py` | The proxy's handover brief: one Gemini call with a fixed answer shape, plain-code checks, and the simple rule-based draft as fallback |
| `agents/recommender.py`, `proxy_ranker.py` | The rule-based recommender (also the fallback) and proxy ranking |
| `config/settings.toml` | Tunable values: reminder milestones, urgency lines, reschedule window, ranking weights, word lists, AI model and timeouts. Edit, restart, done. Read through `app/settings.py` |
| `seed/seed.json` | The demo company: 18 people (some only in the directory, for outside proxies), events with meeting notes, 2 absences |

## Demo scenarios in the seed data
- **Priya** (`p_priya`) is out Oct 20–22, planned: the stand-ups are handled automatically, the Budget Review gets a proxy suggestion from shared summaries, the Vendor Decision falls back to the reporting line, the Design Review's notes are not shared with her, and the Tech Talk is a general event.
- **Kiran** (`p_kiran`) is out suddenly Oct 12–13: items go to the organizers.
- **Neha** (`p_neha`) is unrelated: nothing to do.
- "Now" is fixed at 2026-10-11 in `.env.example`, so the demo is stable.

## Cloud Run
`gcloud run deploy close-the-gap-api --source .` builds the `Dockerfile` in the cloud (`.gcloudignore` keeps `.venv`, `.env`, tests and local scripts out); Cloud Run sets `PORT`. Set `GOOGLE_CLOUD_PROJECT`, `AI_ENABLED`, `NOW` and `CORS_ORIGINS` as environment variables, keep one instance (`--min-instances 1 --max-instances 1`) while data is in memory, keep the CPU allocated (`--no-cpu-throttling`) so background AI analysis keeps running between requests, and give the service account the Vertex AI User role (`roles/aiplatform.user`).
