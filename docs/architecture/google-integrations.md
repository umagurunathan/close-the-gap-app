---
type: Architecture Component
title: Google Calendar and Google Meet integrations
description: Per-person Calendar OAuth, encrypted tokens, event import and write-back (create, move, cancel, add attendee) for the company area, and the hidden Meet transcript import.
resource: ../../backend/app/google_calendar.py
tags: [google-calendar, google-meet, oauth, integration, company-area]
sources:
  - resource: ../../backend/app/google_calendar.py
  - resource: ../../backend/app/google_meet.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/main.py
  - resource: ../../backend/README.md
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Google Calendar and Google Meet integrations

Both integrations belong to the **company area only**. `create_app` binds them to `company_svc`. Each person authorises **their own** account: there is no domain-wide or admin access.

## Google Calendar (`app/google_calendar.py`)

### Enabling

- **Hosted** (`hosted_enabled()`): `GOOGLE_CALENDAR_ENABLED=true`, Firebase auth enabled, and a `FirestoreStore`.
- **Local loopback-only demo**: `GOOGLE_CALENDAR_LOCAL_DEMO_ONLY=true` with `STORE=memory` and a `http://localhost:8000/...` redirect URI. Never set it on Cloud Run.
- `configured()` also needs `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_CALENDAR_REDIRECT_URI` and `GOOGLE_TOKEN_ENCRYPTION_KEY` (a Fernet key).

### OAuth

- Scopes: `https://www.googleapis.com/auth/calendar.events` and `userinfo.email`, with `access_type=offline` and `prompt=consent`. Only the **primary calendar** is used.
- **State**: base64 JSON `{personId, issuedAt, nonce}`, HMAC-SHA256 signed with the client secret. It **expires after 10 minutes**.
- The callback (`GET /integrations/google-calendar/callback`, public) exchanges the code. It requires **the Google account's email to equal the person's directory email**, and redirects to `WEB_APP_URL?calendar=connected|error`.
- Tokens are **Fernet-encrypted** before storage (`calendar_connections`). They refresh automatically within 60 s of expiry, and the old refresh token is kept if Google omits a new one.

### Sync (`POST /integrations/google-calendar/sync`)

The web app also runs it once automatically after connecting.

- `list_events` reads the primary calendar from **30 days back to 365 days ahead** (single events, including deleted ones, paged).
- `Service.sync_google_events` handles each Google entry:

| Google entry | Effect |
|---|---|
| `eventType` in `NOT_MEETINGS` (`outOfOffice`, `focusTime`, `workingLocation`, `birthday`) | Not a meeting. Skipped, and an earlier import is removed with its cards. **An out-of-office entry is not read as an absence** |
| `status = cancelled` | The matching event is cancelled. Open cards become `cancelled` (`decidedBy = "system"`) and requests are withdrawn |
| An event already in the app (same local id or `googleEventId`) | Updated, not imported twice. It keeps its notes and Meet URL. Each card's snapshot follows. A rescheduled card's `rescheduledTo` follows Google's time |
| A new event | Imported (`calendar_event`). The organizer must be the owner or a directory person; attendees are matched by email; unknown people are dropped; all-day dates become midnight UTC. Local id is `gcal:` + sha256 of iCalUID (+ original start) |

- Each imported or updated event is then checked with `_scan_event` (someone already out → cards and an organizer email).
- The response is `{added, updated, skipped, affectedItems}`.

### Write-back

It always runs **before** the app's own change. The organizer's calendar must be the connected owner (`googleCalendarOwnerId == organizerId`). Otherwise the app reports "The organizer must sync their Google Calendar before changing this meeting".

| App action | Google call |
|---|---|
| Schedule a meeting (`POST /events`, when connected) | `create_event`: POST with `sendUpdates=all`. Google sends the invitations. If the app then fails, the Google event is deleted again (rollback) |
| Reschedule | `update_event`: PATCH with `sendUpdates=all`. If Google refuses, nothing changes in the app |
| Cancel | `delete_event`. 404/410 count as already deleted. Done once per meeting |
| Add an attendee, or an outside proxy | `add_attendee` (a proxy is added as optional) |

Integration errors become **HTTP 503** (`CalendarIntegrationError`).

**Limits:**
- Sync is on demand; there are no push notifications.
- Reschedule suggestions use the app's stored meetings, not a free/busy query.

## Google Meet transcripts (`app/google_meet.py`): built, hidden

- The organizer links a Meet URL to a meeting (`PUT /items/{id}/meet`). It must be `https://meet.google.com/<code>`.
- The organizer connects with scope `meetings.space.readonly`. The callback is `GOOGLE_OAUTH_REDIRECT_URI`, and the same OAuth client and Fernet key are used.
- `POST /items/{id}/meet/import` picks a transcript:
  - the conference record closest to the meeting time, within ±2 h;
  - its latest `FILE_GENERATED` transcript.

  The transcript is stored as a meeting summary with readers chosen by the organizer (invitees only). Importing again replaces it.
- The web app hides the button (`SHOW_MEET_IMPORT = false` in `web/src/components/Summaries.jsx`), because transcripts exist only on paid Workspace accounts. The endpoints work.

## Related
- [Schedule a meeting flow](../flows/schedule-a-meeting.md)
- [Reschedule search](reschedule-search.md)
- [Environment variables](../config/environment-variables.md)
- [Deployment](../operations/deployment.md)
