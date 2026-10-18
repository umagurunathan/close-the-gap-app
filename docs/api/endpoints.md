---
type: API Reference
title: HTTP endpoints
description: All 44 FastAPI endpoints grouped by purpose, with identity requirements, request and response shapes, and the Service method behind each.
resource: ../../backend/app/main.py
tags: [api, http, fastapi, reference]
sources:
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/models.py
  - resource: ../../backend/app/firebase_auth.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# HTTP endpoints

The live, try-it-in-the-browser reference is **`/docs`** on a running backend (`http://localhost:8000/docs`). This page is the map. It lists 44 routes, three of them hidden from the schema.

- **Identity** (`me`): either a verified Firebase sign-in (company area), or a guest's `X-Person-Id: p_…`, which must be a demo person. Without either the response is 401. See [Auth and access](../architecture/auth-and-access.md).
- **Area**: chosen per request (signed in → company, guest → demo). Even endpoints that need no identity read the caller's area. See [Areas](../concepts/areas.md).
- **Errors**: 404 / 403 / 400 / 503 from `guard()`, 429 from rate limits, with a plain-language `detail`. A `not_in_directory` response also carries `code`.

## Health and public settings

| Method & path | Identity | Returns | Notes |
|---|---|---|---|
| `GET /` | none | `{app, docs, health}` | Hidden |
| `GET /health` | none | `{ok, store}` | `store` is the store class name, so it shows the live site uses Firestore |
| `GET /settings/public` | none | `{pastDays, suddenNoticeHours, refreshWhileAnalysingSeconds, messageHideSeconds, autoRefreshSeconds, theme, today}` | Read by the web app at load |
| `GET /session` | none | `{signedIn, personId, area}` | |

## People and identity

| Method & path | Identity | Returns | Service |
|---|---|---|---|
| `GET /people` | none | `list[Person]`, groups included | `store.people()` |
| `GET /people/active` | none | `list[str]` of people with something to do now | `active_people` |
| `GET /directory?q=&day=` | me | `list[DirectoryEntry]`: individuals, with `out` that day | `directory` |
| `GET /me` | me | `MeResponse {person, counts}` | `person`, `counts` |

## Absences

| Method & path | Identity | Body → Returns | Service |
|---|---|---|---|
| `GET /absences` | me | `list[Absence]`, current and upcoming (`mine` is ignored) | `absences_for` |
| `POST /absences` | me; **own absence only** (403) | `AbsenceCreate {personId, start, end}` → `AbsenceReport {absence, affected, needDecision}` | `report_absence`, `cards_on_days` |

## Meetings

| Method & path | Identity | Body → Returns | Service |
|---|---|---|---|
| `POST /events` | me; Calendar check if the caller's Google Calendar is connected | `EventCreate {title, description, start, end, attendees}` → `ScheduleResult {eventId, calendarProvider, affected}` | Google `create_event` first (rolled back on failure), then `schedule_meeting` |
| `POST /events/{event_id}/attendees` | me (organizer) | `AttendeeAdd {personId, optional}` → `list[MeetingItem]` | `add_attendee` |

## Cards (items)

| Method & path | Identity | Body → Returns | Service |
|---|---|---|---|
| `GET /items?mode=attendee` | me | `AttendeeItems {needsAction, noActionNeeded{teamCheckins, orgEvents, rescheduledOrCancelled}}` | `attendee_items` |
| `GET /items?mode=organizer` | me | `list[MeetingItem]` | `organizer_items` |
| `GET /items?mode=past` | me | `list[MeetingItem]`, recent past, newest first | `past_items` |
| `POST /items/{item_id}/action` | me | `ActionRequest {action, proxyId?, note?, noteFromAi?, start?}` → `MeetingItem` | `apply_action` |
| `POST /items/{item_id}/reschedule` | me | → `MeetingItem` | `apply_action(reschedule)` |
| `GET /items/{item_id}/proposed-time` | me (absent person or organizer side) | → `ProposedTime {proposedStart, windowUsed, flagged, none}` | `proposed_time` |
| `GET /items/{item_id}/proxy-candidates` | me (absent person or organizer side) | → `list[ProxyCandidate {personId, rank, reason, choice, declined}]` | `proxy_candidates` |
| `GET /items/{item_id}/note-draft/available?proxyId=` | me | → `NoteDraftAvailable {available, reason}` | `note_draft_available` |
| `POST /items/{item_id}/note-draft?proxyId=` | me; **rate limited** (`draft_with_ai`) | → `NoteDraft {draft, engine, model}` | `note_draft` |
| `GET /items/{item_id}/notes` | me (invitees) | → `list[Note]` visible to the caller | `meeting_notes` |
| `POST /items/{item_id}/notes` | me (organizer) | `NoteCreate {text, sharedWith}` → `Note` | `add_meeting_note` |
| `GET /items/{item_id}/agenda` | me (invitees) | → `{agenda}` | `meeting_agenda` |

## Organizer Mode

| Method & path | Identity | Body → Returns | Service |
|---|---|---|---|
| `GET /organizer/meetings` | me | `list[OrganizerMeeting]`: one per meeting | `organizer_meetings` |
| `POST /meetings/{event_id}/action` | me (organizer side) | `MeetingActionRequest {action: reschedule\|cancel\|proceed_without, start?}` → `OrganizerMeeting \| null` | `apply_meeting_action` |

## Proxy requests

| Method & path | Identity | Body → Returns | Service |
|---|---|---|---|
| `GET /proxy-requests?past=` | me | `list[ProxyRequestView {request, item, notesAvailable}]`: upcoming, or recent past with `past=true` | `proxy_requests_for` |
| `POST /proxy-requests/{req_id}/respond` | me (the proxy) | `RespondRequest {response: accepted\|declined}` → `ProxyRequest` | `respond_proxy` |

## History and metrics

| Method & path | Identity | Returns | Service |
|---|---|---|---|
| `GET /history` | me | `list[HistoryEvent]`, last 30 days, newest first | `history_for` |
| `GET /metrics?start=&end=` | none | `Metrics` | `metrics` |
| `GET /metrics/projection` | none | `Projection` | `projection` |

## Google Calendar (company area)

| Method & path | Identity | Returns |
|---|---|---|
| `GET /integrations/google-calendar/status` | me (guests get all false) | `{configured, connected, …}` |
| `GET /integrations/google-calendar/authorize` | signed in + Calendar check | `{authorizationUrl}` |
| `GET /integrations/google-calendar/callback` | public, hidden | 303 to `WEB_APP_URL?calendar=connected\|error` |
| `POST /integrations/google-calendar/sync` | signed in + Calendar check | `{added, updated, skipped, affectedItems}` |

## Google Meet (company area; hidden in the UI)

| Method & path | Identity | Returns |
|---|---|---|
| `GET /integrations/google-meet/status` | me (guests get false) | `{configured, connected}` |
| `GET /integrations/google-meet/authorize` | signed in | `{authorizationUrl}` |
| `GET /integrations/google-meet/callback` | public, hidden | 303 to `?meet=connected\|error` |
| `GET /items/{item_id}/meet` | me | `MeetStatus {meetUrl, configured, connected}` |
| `PUT /items/{item_id}/meet` | signed in (organizer) | `MeetLinkUpdate {meetUrl}` → `MeetStatus` |
| `POST /items/{item_id}/meet/import` | signed in (organizer) | `TranscriptImportRequest {sharedWith}` → `Note` |

## Demo and dev

| Method & path | Identity | Returns | Notes |
|---|---|---|---|
| `GET /dev/outbox` | none | Emails (`to`, `subject`, `body`, `at`) | Signed in: only your own. Guests: demo people's |
| `POST /dev/reset-demo` | guests only (403 when signed in); **rate limited** | `{ok}` | Demo area only. See [Reset demo](../flows/reset-demo.md) |
| `GET /dev/demo-status` | none | `{lastResetAt}` | Never fails |
| `POST /dev/simulate-leave-system` | guests only (404 when signed in) | `LeaveSystemRequest {personId, start, end}` → `Absence` | Creates an absence with `source = leave_system` for any demo person |

## Jobs

| Method & path | Identity | Returns |
|---|---|---|
| `POST /jobs/run-reminders` | Google OIDC token of `REMINDERS_SCHEDULER_SA` with audience `RUN_REMINDERS_AUDIENCE` | `{reminders_sent}`, company area only |

## Related
- [Data models](data-models.md)
- [Backend layers](../architecture/backend-layers.md)
