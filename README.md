# Close the Gap

**Spot the gap early. Keep the meeting going.**

Close the Gap keeps meetings productive when someone is out of office. It identifies every affected meeting early and recommends the most efficient way forward: continue without the person, continue with a briefed proxy, or, only when no better option exists, reschedule. Acting early and putting people in control protects everyone's time.

Built for the Google Cloud AI Builder Cup 2026, theme *Future of Work & Enterprise Productivity*.

When someone goes on leave they usually tell only their manager and reports. Collaborators on other teams find out at the last minute: meetings are cancelled after people have joined, or run without a decision and are followed by a second meeting. Close the Gap acts before that happens, in either order: when a person's absence is reported, and when someone schedules a meeting on a day a key person is already out.

**Live demo:** https://close-the-gap-2026.web.app — no sign-in needed; pick a person in the "Signed in as" menu. Direct links: [Priya, who is going on leave](https://close-the-gap-2026.web.app/?as=p_priya) · [Sam, an organizer](https://close-the-gap-2026.web.app/?as=p_sam&tab=organizer). The demo data resets when the service restarts.

## What it does
- **Finds the affected meetings** from the calendar and recommends one action for each: go on without the person, name a proxy, reschedule, cancel, or "I'll attend" (for the person on leave).
- **Explains every recommendation** with a reason, a confidence level and the sources used. A person always decides; the AI proposes.
- **Optional Google Calendar integration:** locally, connect a demo persona's own account through the loopback-only flow; for the hosted demo, use Firebase Authentication and Firestore with the authenticated OAuth setup in [backend/README.md](backend/README.md).
- **Reads meeting summaries only through each person's own access.** Nothing from a summary reaches someone who couldn't open it, and a missing summary never blocks anything.
- **Handles team check-ins and org-wide events automatically** when it is highly confident (unless the person who is out organizes or hosts the event), and still lets people review and change them.
- **Runs the proxy flow:** the proxy can be anyone in the company directory, on the invite or not, with no organizer approval needed; someone not yet invited is added to the meeting and sent the invite. Covering is always the proxy's choice: they accept or decline, silent proxies get reminders, a declined proxy sends the owner and the organizer back to choose again.
- **Reschedules safely:** same time of day, a day when every required person is free and none is on leave.
- **Both sides can act:** the person who is out and the organizer. Urgency is highlighted for everyone: amber within 3 days, red within 24 hours.
- **One card per meeting for the organizer,** naming everyone who is out, with one recommendation and one-click actions for the whole meeting. Large events (sent to a list, or more than 35 required people) only involve the organizer and the hosts, plus anyone the event names, whom the AI checks.
- **Settled meetings get out of the way:** once a meeting is rescheduled or cancelled it moves to "No action needed" (or "Done" for the organizer), showing the old time struck through and the new one.

## How the AI works
- **A meeting advisor agent built with Google's Agent Development Kit (ADK)** runs on Gemini on Vertex AI. It gets the meeting details and three tools, all bound to one meeting and one viewer: the summaries this viewer may open, the people who could cover (never anyone out that day), and "is this person out that day?". Gemini decides which to use and when to stop (a stand-up needs only the summaries; a proxy needs the candidate list) and returns a structured answer: the action, a one-line reason, a confidence level and, when useful, a suggested proxy. Privacy is enforced by the tools, so the agent cannot see more than the person it advises.
- **Pages never wait for the AI:** a card first shows the rule-based suggestion marked "AI analysing…", the agent works on a few cards at a time in the background, and each card updates by itself when its answer arrives.
- **Plain-code checks run on every answer** before anyone sees it: a suggested proxy must be a real candidate and not out that day, a proxy chosen without summaries is never high confidence, and only high-confidence answers are handled automatically. If a check changes the answer, the card says so.
- **The app never depends on the AI to work:** if the agent fails, a single Gemini call answers; if that fails too, the rule-based recommendation is shown and labelled. Answers are cached until the meeting or the summaries change.
- **Gemini drafts the proxy's handover brief:** what the meeting is for, what the proxy covers, what was decided and what is still open, from summaries that both the sender and the chosen proxy can open. The sender reviews and edits it before sending; when a draft is not available, the screen says why.
- Each card shows where its recommendation came from ("Gemini 2.5 Flash · ADK agent", "Adjusted by rules", or "Rule-based") and, in its details, what the agent looked up.

## Run it locally (two terminals)

**1. Backend** (Python 3.13, FastAPI) — http://localhost:8000, live API docs at `/docs`
```powershell
cd backend
py -3.13 -m venv .venv                                          # once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # once
Copy-Item .env.example .env                                     # once
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
The AI is off by default, so the app runs with the rule-based recommendations and no cloud account. To use Gemini, set `GOOGLE_CLOUD_PROJECT` in `.env` to a project with the Vertex AI API enabled, sign in once with `gcloud auth application-default login`, and start the backend with `$env:AI_ENABLED="true"`.

**2. Web app** (React + Vite) — http://localhost:5173
```powershell
cd web
npm install      # once
npm run dev
```

Use the "Signed in as" dropdown to switch person: Priya (planned leave), Arjun (leave where the AI visibly beats simple rules), Kiran (sudden absence), Sam (organizer), Meena (proxy), Neha (unrelated). "Reset demo" restores the demo data and lets the AI analyse everything again. The "Schedule a meeting" and "Report an absence" buttons let you try both directions. A link can open the app as someone, on a tab: `?as=p_sam&tab=organizer`.

## Deploy
- **Backend → Cloud Run** (from `backend/`): `gcloud run deploy close-the-gap-api --source . --region asia-south1 --allow-unauthenticated --min-instances 1 --max-instances 1 --concurrency 1 --no-cpu-throttling --set-env-vars "GOOGLE_CLOUD_PROJECT=<project>,AI_ENABLED=true,CORS_ORIGINS=<web app URL>"`. One instance and one concurrent request keep the global in-memory seed mode consistent; CPU stays allocated for background AI analysis. The service account needs the Vertex AI User role to call Gemini.
- **Web app → Firebase Hosting** (from `web/`): put the backend URL in `.env.production`, then `npm run build` and `firebase deploy --only hosting`.

Google Calendar supports local demo OAuth and an authenticated hosted Firestore mode. For the hosted global
Seed-file/Firestore selector, cross-project IAM, Firebase Authentication, presenter allowlisting, and Calendar OAuth
setup, follow [backend/README.md](backend/README.md).

## Tests
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## Layout
```
backend/   FastAPI app, agents, seed data, tests   (see backend/README.md)
web/       React app: Attendee Mode, Organizer Mode, Proxy Requests, Past
```

## Built with
This list shows what is built today and is updated as the project ships.
- **AI:** Gemini 2.5 Flash on Vertex AI (asia-south1); Agent Development Kit (ADK) for the meeting advisor agent; Google Gen AI SDK (`google-genai`) with structured output for the single-call fallback
- **Google Cloud:** Cloud Run (backend), Cloud Build and Artifact Registry (container builds), Firebase Hosting (web app), Cloud Logging
- **Backend:** Python 3.13, FastAPI, pydantic, pytest
- **Web app:** React 19, Vite
- **Development tools:** Google Antigravity, Claude Code (AI coding assistants), Visual Studio Code, Git
