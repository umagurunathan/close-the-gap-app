# Close the Gap — backend

Python 3.13 · FastAPI. Runs locally with no cloud account; deployed on Cloud Run. Settings come from environment variables (secrets from Secret Manager on Cloud Run) and the tunable numbers from `config/settings.toml`.

## Run it
```powershell
cd backend
py -3.13 -m venv .venv                                          # once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # once
Copy-Item .env.example .env                                     # once
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
- Live API docs (every endpoint and its shapes; try them in the browser): http://localhost:8000/docs
- Without sign-in, a request acts as a demo person named in the header `X-Person-Id: p_priya` (the demo people are in `seed/seed.json`).
- Emails are not sent; the ones the app would send are listed at `GET /dev/outbox`.
- By default (`STORE=memory`) the demo data lives in memory and is loaded from the seed at start; **Reset demo data** (`POST /dev/reset-demo`) loads it again.

## The two areas
One backend serves two areas, never mixed:
- **Demo area** (`FIRESTORE_DEMO_WORKSPACE_ID`, default `guest`): every request without a sign-in, acting as one of the demo people. Its data is loaded only by **Reset demo data**, from `seed/seed.json`. The time of the last reset is kept and shown to every visitor (`GET /dev/demo-status`).
- **Company area** (`FIRESTORE_WORKSPACE_ID`, default `company`): people who sign in with Google and are in the private company directory (`COMPANY_DIRECTORY`, a JSON list kept in Secret Manager or the git-ignored `.env`, never in the code). Each sees only their own work. It holds the directory people and what they do in the app, including their Google Calendar sync. It is never seeded or reset, and uses the real clock.

Each request is routed to one area (`app/main.py`, `_AreaRouter`). With Firestore, every record carries its area in `workspaceId` and in its document id (`guest__…`, `company__…`). The backend refuses to start if the two areas have the same name, and Reset demo data refuses to run anywhere but the demo area. Starting the backend writes nothing.

## Firestore
```dotenv
STORE=firestore
GOOGLE_CLOUD_PROJECT=your-project-id
FIRESTORE_DATABASE=your-database-id
# only when the database is in another project than Cloud Run:
FIRESTORE_PROJECT_ID=your-firestore-project-id
```
Locally, sign in once with `gcloud auth application-default login`. On Cloud Run, grant the service account `roles/datastore.user` in the project that holds the database. Collections: `people`, `events` (with their meeting summaries), `absences`, `items` (one card per affected meeting and absent person), `proxy_requests`, `history`, `metadata`, `calendar_connections`, `meet_connections`. Firestore permissions are project-wide here, so the area boundary is enforced by the backend; database credentials are never given to the web app.

**Read cache for one request** (`[store] request_cache`, environment `STORE_REQUEST_CACHE=false` to switch off): while one request runs, each collection is read at most once and the request's own writes update what it has read; nothing is kept after the request, so data is never stale. Background AI threads read Firestore directly.

## Sign in with Google (Firebase Authentication)
```dotenv
FIREBASE_AUTH_ENABLED=true
FIREBASE_PROJECT_ID=your-firebase-project
COMPANY_DIRECTORY=[{"id":"p_...","name":"...","email":"...","title":"...","department":"...","managerId":null}]
```
The backend verifies the Firebase ID token on every request. The verified email must match exactly one person in the directory, and a signed-in person can only act as themselves. A Google account that is not in the directory gets a polite message and can keep using the demo. The web app needs the Firebase web settings (public browser configuration, not credentials) in `web/.env.local` / `web/.env.production`: `VITE_FIREBASE_AUTH_ENABLED`, `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID`. In Firebase, enable the Google sign-in method and add the Hosting domain to the authorized domains.

## Google Calendar (company area only)
```dotenv
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_REDIRECT_URI=https://your-cloud-run-url/integrations/google-calendar/callback
GOOGLE_OAUTH_CLIENT_ID=...          # Secret Manager on Cloud Run
GOOGLE_OAUTH_CLIENT_SECRET=...      # Secret Manager on Cloud Run
GOOGLE_TOKEN_ENCRYPTION_KEY=...     # Secret Manager on Cloud Run (a Fernet key)
WEB_APP_URL=https://your-web-app
```
- Each signed-in person connects their own Google account (OAuth web client, scopes `calendar.events` and `userinfo.email`, primary calendar only; no domain-wide access). The Google account must match the person's directory email. The callback is protected by signed, expiring state; refresh tokens are encrypted before they are stored.
- **Sync** imports meetings from 30 days back to a year ahead, right after connecting and with **Sync Google Calendar**. Organizers and invitees are matched by email to the directory; others are left out. A meeting already in the app (by its Google event id) is updated, not imported twice.
- **Not meetings:** out-of-office, focus-time and working-location entries (and birthdays) are skipped; one imported before this rule existed is removed with its cards. An out-of-office entry is **not** read as an absence: absences come only from **Report an absence**.
- **Schedule a meeting** creates a real Google Calendar invitation from the organizer's calendar (`sendUpdates=all`), so Google sends it to the guests. Rescheduling, canceling and adding an uninvited proxy update the Google event when the organizer's calendar is the connected one.
- Calendar does not run locally against the hosted keys: they stay in Secret Manager. For a local try, a loopback-only mode exists (`GOOGLE_CALENDAR_LOCAL_DEMO_ONLY=true` with a `http://localhost:8000/...` redirect URI); never set it on Cloud Run.
- Limits: sync is on demand (no push notifications); reschedule suggestions use the meetings stored in the app, not a live free/busy query.

## Gemini through Vertex AI
The AI is off by default (`[ai] enabled = false` in `config/settings.toml`), so the app and the tests run without a cloud account. To switch it on: set `GOOGLE_CLOUD_PROJECT`, enable the Vertex AI API, run `gcloud auth application-default login` once (on Cloud Run, the service account needs `roles/aiplatform.user`), and start with `$env:AI_ENABLED="true"`. There is no API key. The model and region are in `[ai]` (`gemini-2.5-flash`, `asia-south1`); `AI_MODEL` overrides the model.

An older optional proxy ranker inside the rule-based fallback (`LLM_PROVIDER=vertex`, `VERTEX_AI_LOCATION`, `GEMINI_MODEL`) is off by default and not used by the live app.

## Google Meet transcripts (hidden in the app)
The organizer can link a Meet URL to a meeting, connect their Google account (scope `meetings.space.readonly`) and import the transcript as a meeting summary, choosing who may read it. The endpoints work; the web app hides the button for now (`SHOW_MEET_IMPORT` in `web/src/components/Summaries.jsx`). It needs the Google Meet REST API, `GOOGLE_OAUTH_REDIRECT_URI` for its callback, and the same OAuth client and encryption key.

## Test it
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # once: adds pytest
.\.venv\Scripts\python.exe -m pytest -q
```
114 tests, offline (AI off; a fake Firestore for the read cache).

## Where things are
| Path | What |
|---|---|
| `app/main.py` | The endpoints, the two areas, sign-in and Calendar wiring |
| `app/service.py` | The logic: scan an absence, check a new meeting, actions, proxy flow, Calendar sync, reminders, metrics |
| `app/models.py` | The data shapes |
| `app/scheduling.py` | Reschedule search: plain code, same time of day ±1 h then ±2 h |
| `app/roles.py` | Who is a key person: required invitees, large events (a list, or more than 35 required people), hosting roles, optional invitees |
| `app/settings.py` | Reads `config/settings.toml`; `AI_ENABLED`, `AI_MODEL` and `STORE_REQUEST_CACHE` in the environment override it |
| `app/config.py` | Environment settings: store, areas, company directory, Firebase, CORS, the demo's fixed "now" |
| `app/store.py`, `app/calendar.py` | In-memory and Firestore adapters (app data; calendar events with their summaries) |
| `app/firestore.py` | Firestore helpers and the per-request read cache |
| `app/firebase_auth.py` | Firebase ID-token check and the match to one directory person |
| `app/google_calendar.py` | Google Calendar OAuth, encrypted token storage, event import and updates |
| `app/google_meet.py` | Google Meet OAuth and transcript import |
| `app/seed.py` | Builds the two areas; **Reset demo data** |
| `app/notify.py` | Email outbox (stand-in for real email) |
| `agents/orchestrator.py` | How each card is analysed: rules when the AI is off or for a large event; otherwise the ADK agent, then (if it fails) one Gemini call with retries, then the rules; the checks run on any AI answer |
| `agents/adk_advisor.py` | The meeting advisor, an ADK agent with three tools bound to one meeting and one viewer: `read_summaries`, `list_proxy_candidates`, `check_if_out` |
| `agents/recommender_ai.py` | The single-call Gemini recommender (the agent's fallback, and `[ai] engine = "genai"`) |
| `agents/guard.py` | Plain-code checks on every AI answer |
| `agents/untrusted.py` | Prompt-injection defence: typed text is wrapped as data; instructions aimed at the AI are spotted |
| `agents/note_drafter.py` | The proxy's handover brief: one Gemini call with a fixed answer shape and checks |
| `agents/fallback/` | **Fallback only** (AI off or unavailable): keyword rules (also shown as "what simple rules would have said"), the proxy panel's order, a note without AI |
| `config/settings.toml` | Tunable values: urgency, reschedule window, ranking, word lists, AI model and timeouts, auto-refresh, the read cache. Edit, restart, done |
| `seed/seed.json` | The demo company: 26 people (some only in the directory, as outside proxies), 35 meetings with summaries, 5 absences, and a handled past week |

## Demo scenarios in the seed data
- **Priya** (`p_priya`), planned leave 20–22 Oct: stand-ups handled automatically; Q4 Budget Review gets a proxy from shared summaries; Design Review's summaries are not shared with her.
- **Meena** (`p_meena`), asked to cover; **Dev** (`p_dev`), a proxy who declines.
- **Sam** (`p_sam`), organizer: one card per meeting with everyone who is out.
- **Arjun** (`p_arjun`), where Gemini changes the rules' answer (sign-offs, an outside customer, a presenter).
- **Kiran** (`p_kiran`), out suddenly 12–13 Oct: the organizer is alerted at once.
- **Lena** (`p_lena`), a week's vacation with a full calendar; **Ben** (`p_ben`), an organizer outside Arjun's team.
- "Now" is fixed at 11 Oct 2026 (`NOW`) in the demo area, so the demo always tells the same story.

## Cloud Run
```powershell
gcloud run deploy close-the-gap-api --source . --region asia-south1 --allow-unauthenticated `
  --min-instances 1 --max-instances 1 --concurrency 20 --no-cpu-throttling `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=<project>,AI_ENABLED=true,NOW=2026-10-11T09:00:00Z,STORE=firestore,FIRESTORE_PROJECT_ID=<firestore-project>,FIRESTORE_DATABASE=<database>,FIRESTORE_WORKSPACE_ID=company,FIRESTORE_DEMO_WORKSPACE_ID=guest,FIREBASE_AUTH_ENABLED=true,FIREBASE_PROJECT_ID=<firebase-project>,GOOGLE_CALENDAR_ENABLED=true,GOOGLE_CALENDAR_REDIRECT_URI=https://<cloud-run-url>/integrations/google-calendar/callback,WEB_APP_URL=<web-app-url>,CORS_ORIGINS=<web-app-url>" `
  --set-secrets "COMPANY_DIRECTORY=company-directory:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,GOOGLE_TOKEN_ENCRYPTION_KEY=google-token-encryption-key:latest"
```
- `--source .` builds the `Dockerfile` in the cloud (`.gcloudignore` keeps `.venv`, `.env` and tests out). A later redeploy keeps every setting it does not name.
- **One instance, CPU always on:** background AI analysis keeps running between requests, and the AI's answers and the demo email outbox live in the instance's memory. **20 requests at a time** with the per-request read cache.
- The service account needs `roles/aiplatform.user`, `roles/datastore.user` (in the database's project) and `roles/secretmanager.secretAccessor` on the secrets. Keep secret values in Secret Manager versions, never in deployment arguments, source control or the web app.
