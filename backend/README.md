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
| `app/calendar.py` | Simulated calendar. A real calendar can be added behind the same methods |
| `app/store.py` | Storage interface. In-memory now; Firestore can be added behind it |
| `app/notify.py` | Email outbox (stand-in for real email) |
| `agents/` | Orchestrator, recommender, proxy ranker, note drafter. Rule-based stand-ins for now, to be replaced by ADK + Gemini agents with the same function signatures |
| `config/settings.toml` | Tunable values: reminder milestones, urgency lines, reschedule window, ranking weights, word lists. Edit, restart, done. Read through `app/settings.py` |
| `seed/seed.json` | The demo company: 9 people, events with meeting notes, 2 absences |

## Demo scenarios in the seed data
- **Priya** (`p_priya`) is out Oct 20–22, planned: the stand-ups are handled automatically, the Budget Review gets a proxy suggestion from shared summaries, the Vendor Decision falls back to the reporting line, the Design Review's notes are not shared with her, and the Tech Talk is a general event.
- **Kiran** (`p_kiran`) is out suddenly Oct 12–13: items go to the organizers.
- **Neha** (`p_neha`) is unrelated: nothing to do.
- "Now" is fixed at 2026-10-11 in `.env.example`, so the demo is stable.

## Cloud Run
`docker build` uses the `Dockerfile`; Cloud Run sets `PORT`. Set `STORE`, `CORS_ORIGINS` and any keys as environment variables or Secret Manager entries.
