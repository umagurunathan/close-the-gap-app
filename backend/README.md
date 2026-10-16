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

## Use Firebase Authentication
The optional Firebase Authentication mode signs users in with Google and verifies the Firebase ID token on every
backend request. The verified email must match exactly one individual in the app directory; the client cannot choose
another persona with `X-Person-Id`. The local demo persona selector remains available while authentication is off.
At the hosted sign-in page, visitors can either continue with Google or continue as a guest using fictional demo
data. Google sign-in resolves the company person from the verified email. Connecting Google Calendar is a separate
OAuth consent; after a successful connection, the app automatically imports that calendar into the company workspace.
Only attendees whose email addresses match directory people are included in the imported meeting.

For the hosted app, configure a Firebase Web app in the `close-the-gap-2026` Firebase project, enable **Google** under
Authentication → Sign-in method, and add `close-the-gap-2026.web.app` to Authentication → Settings → Authorized domains.
Set the Web app's public config values in `web/.env.production`:
```dotenv
VITE_FIREBASE_AUTH_ENABLED=true
VITE_FIREBASE_API_KEY=your-web-api-key
VITE_FIREBASE_AUTH_DOMAIN=close-the-gap-2026.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=close-the-gap-2026
VITE_FIREBASE_APP_ID=your-web-app-id
```
These are browser configuration values, not service-account credentials. Then update the Cloud Run service environment:
```powershell
gcloud run services update close-the-gap-api --region asia-south1 `
  --update-env-vars FIREBASE_AUTH_ENABLED=true,FIREBASE_PROJECT_ID=close-the-gap-2026
```
Build and deploy Hosting after the Firebase Web app config is in place:
```powershell
cd web
npm run build
firebase deploy --only hosting
```
For local auth testing, use the same Web app config in `web/.env.local`, set `FIREBASE_AUTH_ENABLED=true` and
`FIREBASE_PROJECT_ID=close-the-gap-2026` in `backend/.env`, then restart both apps. A verified Google email must belong
to exactly one person in the backend directory. With Firestore, update that person's existing `people` document if its
email differs from the seed.

## Use Cloud Firestore
The backend can persist its data in a Firestore Native database. Create `backend/.env` from `.env.example`, then set:
```dotenv
STORE=firestore
GOOGLE_CLOUD_PROJECT=your-project-id
FIRESTORE_DATABASE=your-database-id
FIRESTORE_WORKSPACE_ID=company
```
For local development, authenticate with Application Default Credentials using `gcloud auth application-default login`.
On Cloud Run, grant the service account the Firestore User role instead of using a local key file. Starting the
backend writes nothing to Firestore: the demo data is loaded into the demo area only by **Reset demo data**, and the
company area holds only the people in the company directory and what they do in the app (including their synced
Google Calendar meetings). The backend refuses to start if the two areas have the same name.
If Firestore is in a different project from Cloud Run, set `FIRESTORE_PROJECT_ID` to that project and grant the Cloud
Run service account `roles/datastore.user` there. `GOOGLE_CLOUD_PROJECT` continues to identify the Cloud Run project.

Both services use the same Firestore collection names: `people`, `events`, `absences`, `items`, `proxy_requests`,
`history`, `metadata`, `meet_connections`, and `calendar_connections`. Each record carries a `workspaceId` and uses a
workspace-qualified Firestore document ID (`company__...` or `guest__...`). The authenticated app uses `company`;
the unauthenticated public demo uses `guest`. The backend filters every collection read by workspace, so public guest
sessions do not read company calendars, tokens, absences, or actions. Firestore IAM is project-wide in this setup;
the workspace boundary is enforced by the backend, not Firestore IAM.

Deploy the signed-in service with `FIRESTORE_WORKSPACE_ID=company` and the public service with
`FIRESTORE_WORKSPACE_ID=guest`. The hosted database has been migrated to this layout; legacy unscoped records and
`public_demo_` collections were removed after verifying their workspace-scoped copies. Keep the public service's
dedicated identity and do not attach Calendar OAuth secrets.
Event documents include their notes and `sharedWith` lists. Notes are filtered by the backend before returning them;
Firestore server credentials bypass Firestore Security Rules, so do not expose database credentials to the web app.
In a meeting card's **Meeting notes** section, the organizer can add notes and choose which invitees can read each
one. A note must be shared with every invitee to enable the AI-drafted proxy handover.

## Choose the hosted demo data mode

The hosted top bar can expose **Seed file** and **Calendar + Firestore** buttons to an authorized presenter. This is a
global switch: it changes the data source for every user. The seed option loads `seed/seed.json` into in-memory data;
changes in that mode are temporary. Firestore mode initializes missing records from the same JSON and preserves
existing documents, then stores app changes and Calendar connection tokens in Firestore. Selecting Firestore does not
automatically grant Calendar access: each person still connects their own Google account and presses **Sync Google
Calendar**.

Enable Firebase Authentication and configure these Cloud Run environment variables:
```dotenv
FIREBASE_AUTH_ENABLED=true
FIREBASE_PROJECT_ID=close-the-gap-2026
DATA_MODE_SWITCH_ENABLED=true
DATA_MODE_ADMIN_EMAILS=admin@example.com
STORE=firestore
GOOGLE_CLOUD_PROJECT=your-cloud-run-project
FIRESTORE_PROJECT_ID=your-firestore-project
```
Set the Firestore project separately only when it differs from the Cloud Run project. The selected mode is kept in
Firestore at `metadata/company__demo_mode`, so it survives a Cloud Run restart. While the selector is enabled, configure Cloud
Run with one maximum instance and request concurrency `1`; the seed data is intentionally instance-local, and mode
changes must not race active requests. Only emails in
`DATA_MODE_ADMIN_EMAILS` can change the global mode. Do not configure the selector without Firebase Authentication and
an explicit presenter allowlist.

The Cloud Run service account needs Firestore access in the Firestore-owning project. Enabling the Firestore API and
granting that service identity access are separate from the Gmail account used to authorize Calendar. Existing
Firestore `people` documents are not overwritten by the seed; their email addresses must match the corresponding
verified Firebase/Google account.

## Use Google Calendar

For local testing, Calendar remains limited to loopback requests and the in-memory store. Enable the **Google Calendar
API** and add this redirect URI to the OAuth Web client:
`http://localhost:8000/integrations/google-calendar/callback`. In `backend/.env`, set the existing OAuth client ID,
client secret, and Fernet encryption key described below, plus:
```dotenv
GOOGLE_CALENDAR_LOCAL_DEMO_ONLY=true
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/integrations/google-calendar/callback
```

For the hosted mode, use a Google OAuth **Web application** client, enable the Google Calendar API in the project that
owns that client, and add the exact Cloud Run callback URL:
`https://your-cloud-run-url/integrations/google-calendar/callback`. Configure these Cloud Run values/secrets:
```dotenv
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_REDIRECT_URI=https://your-cloud-run-url/integrations/google-calendar/callback
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_TOKEN_ENCRYPTION_KEY=...
WEB_APP_URL=https://close-the-gap-2026.web.app
```
Keep `GOOGLE_CALENDAR_LOCAL_DEMO_ONLY` unset in Cloud Run. Hosted Calendar requires Firebase Authentication, Firestore
mode, and the encrypted token store. The OAuth callback is validated with signed, expiring state; the Google account
must match the signed-in directory person's email. Each participant authorizes their own account; the app does not use
domain-wide/admin access. OAuth requests `calendar.events` permission and accesses only the person's primary calendar.
The local-only flag is not a substitute for authentication and must not be enabled on Cloud Run.

Calendar sync imports the primary calendar's meetings from the previous 30 days through the next 365 days. The app
matches attendees and organizers by email against the company directory; people not in that directory are omitted from
the app's attendee model. The **Schedule a meeting** form creates a real Google Calendar event and sends invitations
when the signed-in person has connected. Rescheduling, cancellation, and adding an uninvited proxy update the Google
event only when the organizer's primary calendar is the connected owner. Existing events must be synced by the
organizer before the app can change them. Calendar changes are on demand; push notifications and live sync are not
implemented. Reschedule suggestions use events currently stored in the app, not a live Google FreeBusy query; sync
every relevant participant's calendar before relying on a proposed slot.

## Import a Google Meet transcript
The organizer can link a Meet URL to a meeting card, connect their Google account, and import the generated transcript
after the meeting. This first version imports on demand; it does not capture live audio or poll for transcripts in the
background. The transcript is saved as a meeting note; the organizer chooses its readers. Google Meet transcripts are
not available until transcription was enabled and Google has generated the artifact.

1. In Google Cloud Console, enable the **Google Meet REST API** and configure the OAuth consent screen for your
   Workspace users. Create an OAuth **Web application** client with this exact local redirect URI:
   `http://localhost:8000/integrations/google-meet/callback`.
2. Generate an encryption key:
   ```powershell
   .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
3. Put the OAuth client ID, client secret and generated encryption key in `backend/.env` (never in the web app):
   ```dotenv
   GOOGLE_OAUTH_CLIENT_ID=your-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/integrations/google-meet/callback
   GOOGLE_TOKEN_ENCRYPTION_KEY=your-generated-fernet-key
   WEB_APP_URL=http://localhost:5173
   ```
   Store the encryption key and OAuth client secret in Secret Manager in hosted deployments. OAuth refresh tokens
   are encrypted before storage; keep the encryption key stable so saved connections can be decrypted.
   Google account verification must match the organizer's email in the app: sign in with Google as a person in the
   company directory (demo people cannot connect Google services).
4. Restart the backend. As the meeting organizer, open the card's **Meeting notes → Google Meet capture**, save the
   meeting's `https://meet.google.com/...` link, and select **Connect Google Meet**. Sign in with the Google account
   that owns/organized the Meet. The app requests the read-only `meetings.space.readonly` scope.
5. After the meeting and transcript generation finish, choose the transcript readers and click **Import transcript**.
   Importing again updates the same transcript note rather than creating a duplicate.

The Google account authorizing access must be able to access the conference record and generated transcript. Meet
transcription depends on Workspace edition, administrator policy and the meeting's transcription settings. This app's
persona switcher is demo authentication; replace it with real user authentication before deploying this integration
for multiple users.

## Use Gemini through Vertex AI
The default `LLM_PROVIDER=rules` makes no model calls. To opt into Gemini proxy suggestions, enable the Vertex AI API,
grant the local ADC identity or Cloud Run service account the Vertex AI User role, then set `LLM_PROVIDER=vertex` in
`backend/.env`. `GOOGLE_CLOUD_PROJECT`, `VERTEX_AI_LOCATION`, and `GEMINI_MODEL` select the project, model endpoint,
and model (defaults: `asia-southeast1` and `gemini-3.8-flash`). Vertex calls may incur charges.

Gemini receives only the summaries already visible to the decision-maker and the rule-ranked meeting invitees. Its
response must name an eligible candidate and quote exact note text; invalid or unavailable responses fall back to the
rule-based ranker. A person still chooses and sends the proxy request.

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
| `app/calendar.py` | In-memory and Firestore calendar adapters, including event notes |
| `app/store.py` | In-memory and Firestore app-state adapters |
| `app/google_calendar.py` | Local and hosted Google Calendar OAuth, encrypted token storage and event sync |
| `app/data_mode.py` | Firestore-backed global selection of seed-file vs Firestore mode |
| `app/google_meet.py` | Google OAuth, encrypted token storage and Meet transcript import |
| `app/notify.py` | Email outbox (stand-in for real email) |
| `agents/orchestrator.py` | Decides how each card is analyzed: rules when the AI is off or for a large event; otherwise the ADK agent, then (if it fails) one Gemini call with retries, then the rules; the checks run on any AI answer |
| `agents/adk_advisor.py` | The meeting advisor, an ADK agent with four tools bound to one meeting and one viewer (`get_meeting`, `read_summaries`, `list_proxy_candidates`, `check_if_out`) |
| `agents/recommender_ai.py` | The single-call Gemini recommender (the agent's fallback, and `[ai] engine = "genai"`): builds the prompt (only summaries the viewer can open, candidates who are not out that day), asks for a structured answer |
| `agents/guard.py` | Plain-code checks on every AI answer (proxy must be a valid candidate, confidence caps, auto-handling only at high confidence, text that tries to instruct the AI is flagged for a person) |
| `agents/untrusted.py` | Prompt-injection defence: wraps typed text (agenda, summaries) in markers, tells Gemini it is data not instructions, and spots instructions aimed at the AI |
| `agents/note_drafter.py` | The proxy's handover brief: one Gemini call with a fixed answer shape and plain-code checks |
| `agents/fallback/` | **Fallback only** (AI off or unavailable): `rules_recommender.py` (keyword rules; also shown on cards as "what simple rules would have said"), `candidate_order.py` (orders the proxy panel's list), `simple_note.py` (a note without AI) |
| `config/settings.toml` | Tunable values: reminder milestones, urgency lines, reschedule window, ranking weights, word lists, AI model and timeouts. Edit, restart, done. Read through `app/settings.py` |
| `seed/seed.json` | The demo company: 18 people (some only in the directory, for outside proxies), events with meeting notes, 2 absences |

## Demo scenarios in the seed data
- **Priya** (`p_priya`) is out Oct 20–22, planned: the stand-ups are handled automatically, the Budget Review gets a proxy suggestion from shared summaries, the Vendor Decision falls back to the reporting line, the Design Review's notes are not shared with her, and the Tech Talk is a general event.
- **Kiran** (`p_kiran`) is out suddenly Oct 12–13: items go to the organizers.
- **Neha** (`p_neha`) is unrelated: nothing to do.
- "Now" is fixed at 2026-10-11 in `.env.example`, so the demo is stable.

## Cloud Run
`gcloud run deploy close-the-gap-api --source .` builds the `Dockerfile` in the cloud (`.gcloudignore` keeps `.venv`, `.env`, tests and local scripts out); Cloud Run sets `PORT`. Set `GOOGLE_CLOUD_PROJECT`, `AI_ENABLED`, `NOW` and `CORS_ORIGINS` as environment variables, keep one instance (`--min-instances 1 --max-instances 1`) and request concurrency `1` while the global in-memory mode is enabled, keep the CPU allocated (`--no-cpu-throttling`) so background AI analysis keeps running between requests, and give the service account the Vertex AI User role (`roles/aiplatform.user`).

The unauthenticated public demo uses a separate Cloud Run service and writes to the `guest` workspace in the common Firestore collections. Configure `STORE=firestore`, `FIRESTORE_PROJECT_ID`, `FIRESTORE_DATABASE=meetingnotes`, and `FIRESTORE_WORKSPACE_ID=guest`; leave Firebase Authentication, the global data-mode switch, AI, and Google Calendar disabled. Demo directory emails are rewritten to reserved `.invalid` addresses. The public service needs `roles/datastore.user` in the Firestore project. Its workspace boundary is enforced by the backend because Firestore IAM is project-wide here. Keep its dedicated service identity, never expose company workspace records from guest API responses, and never store real employee data or Calendar tokens in the guest workspace. Set `CORS_ORIGINS=https://close-the-gap-2026.web.app`, `--max=1`, `--concurrency=1`, and `--min=0`. Set Hosting's `VITE_DEMO_API_URL` to this service's URL. Guest data is initialized from `seed/seed.json`; subsequent guest changes persist and are shared with visitors. Do not attach Calendar OAuth secrets.

For hosted Calendar, store `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `GOOGLE_TOKEN_ENCRYPTION_KEY` in Secret Manager; do not put their values in deployment arguments, source control, or frontend configuration. Create the secrets and add a version using the Google Cloud Console or Secret Manager CLI. Grant the Cloud Run runtime service account `roles/secretmanager.secretAccessor` on all secrets. Then reference the secret IDs when deploying:
```powershell
gcloud run deploy close-the-gap-api --source . --project <cloud-run-project> --region asia-south1 `
  --allow-unauthenticated --min-instances 1 --max-instances 1 --concurrency 1 --no-cpu-throttling `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=<cloud-run-project>,FIRESTORE_PROJECT_ID=<firestore-project>,FIRESTORE_DATABASE=(default),STORE=firestore,FIREBASE_AUTH_ENABLED=true,FIREBASE_PROJECT_ID=close-the-gap-2026,DATA_MODE_SWITCH_ENABLED=true,DATA_MODE_ADMIN_EMAILS=admin@example.com,GOOGLE_CALENDAR_ENABLED=true,GOOGLE_CALENDAR_REDIRECT_URI=https://<cloud-run-url>/integrations/google-calendar/callback,WEB_APP_URL=https://close-the-gap-2026.web.app,CORS_ORIGINS=https://close-the-gap-2026.web.app" `
  --set-secrets "GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,GOOGLE_TOKEN_ENCRYPTION_KEY=google-token-encryption-key:latest"
```
Replace every placeholder with the confirmed deployment values. Enable the Cloud Run, Firestore, Secret Manager, and Google Calendar APIs in their respective projects. The Firestore-owning project must grant the Cloud Run service identity `roles/datastore.user`; cross-project secrets likewise require secret accessor permissions in the project holding those secrets. Keep OAuth credentials and encryption keys in Secret Manager versions, and rotate them there rather than editing the service definition with plaintext values.
