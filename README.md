# Close the Gap

**Spot the gap early. Keep the meeting going.**

Close the Gap keeps meetings productive when someone is out of office. It identifies every affected meeting early and recommends the most efficient way forward: continue without the person, continue with a briefed proxy, or, only when no better option exists, reschedule. Acting early and putting people in control protects everyone's time.

Built for the Google Cloud AI Builder Cup 2026, theme *Future of Work & Enterprise Productivity*.

When someone goes on leave they usually tell only their manager and reports. Collaborators on other teams find out at the last minute: meetings are cancelled after people have joined, or run without a decision and are followed by a second meeting. Close the Gap acts before that happens, in either order: when a person's absence is reported, and when someone schedules a meeting on a day a key person is already out.

## What it does
- **Finds the affected meetings** from the calendar and recommends one action for each: go on without the person, name a proxy, reschedule, cancel, or "I'll attend" (for the person on leave).
- **Explains every recommendation** with a reason, a confidence level and the sources used. A person always decides; the AI proposes.
- **Reads meeting summaries only through each person's own access.** Nothing from a summary reaches someone who couldn't open it, and a missing summary never blocks anything.
- **Handles routine meetings and general events automatically** when it is highly confident, and still lets people review and change them.
- **Runs the proxy flow:** the proxy can be anyone in the company directory, on the invite or not, with no organizer approval needed; someone not yet invited is added to the meeting and sent the invite. Covering is always the proxy's choice: they accept or decline, silent proxies get reminders, a declined proxy sends the owner and the organizer back to choose again.
- **Reschedules safely:** same time of day, a day when every required person is free and none is on leave.
- **Both sides can act:** the person who is out and the organizer. Urgency is highlighted for everyone: amber within 3 days, red within 24 hours.

## Run it locally (two terminals)

**1. Backend** (Python 3.13, FastAPI) — http://localhost:8000, live API docs at `/docs`
```powershell
cd backend
py -3.13 -m venv .venv                                          # once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # once
Copy-Item .env.example .env                                     # once
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

**2. Web app** (React + Vite) — http://localhost:5173
```powershell
cd web
npm install      # once
npm run dev
```

Use the "Signed in as" dropdown to switch person: Priya (planned leave), Kiran (sudden absence), Sam (organizer), Meena (proxy), Neha (unrelated). The "Schedule a meeting" and "Report an absence" buttons let you try both directions.

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
- **Backend:** Python 3.13, FastAPI, pydantic, pytest
- **Web app:** React 19, Vite
- **Development tools:** Google Antigravity, Claude Code (AI coding assistants), Visual Studio Code, Git
