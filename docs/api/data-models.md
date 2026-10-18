---
type: Data Model
title: Data models (app/models.py)
description: The pydantic enums and models shared by the backend, the API and the web app; camelCase on purpose, with every field of the core records.
resource: ../../backend/app/models.py
tags: [data-model, pydantic, schema, api]
sources:
  - resource: ../../backend/app/models.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Data models (`backend/app/models.py`)

All shapes are pydantic models. **Field names are camelCase on purpose**: they are the same names the API returns and the web app reads, so there is no mapping layer. Times are timezone-aware datetimes in UTC; absence days are dates.

## Enums

| Enum | Values |
|---|---|
| `AbsenceType` | `planned`, `sudden` |
| `AbsenceSource` | `calendar_ooo`, `leave_system`, `manual` |
| `Action` | `attend`, `proceed_without`, `proxy`, `reschedule`, `cancel` |
| `Confidence` | `high`, `medium`, `low` |
| `ItemKind` | `key_meeting`, `team_checkin`, `org_event` |
| `ItemStatus` | `pending_decision`, `auto_handled`, `attending`, `proceeding_without`, `proxy_requested`, `proxy_accepted`, `proxy_declined`, `awaiting_organizer`, `rescheduled`, `cancelled`, `no_slot_found` |
| `ProxyRequestStatus` | `pending`, `accepted`, `declined`, `withdrawn` |

## Core records (stored)

**`Person`**: `id`, `name`, `email`, `title`, `department`, `managerId?`, `timeZone` (default `America/New_York`, not used for display), `workingHours {start "09:00", end "17:30"}`, `isGroup` (a distribution list, never a proxy).
- `DirectoryEntry` = `Person` + `out` (on leave that day).

**`CalEvent`** (calendar): `id`, `seriesId?`, `title`, `description` (the agenda), `start`, `end`, `organizerId`, `attendees: [EventAttendee {personId, optional}]`, `inviteGroup?`, `meetUrl?`, `googleEventId?`, `googleCalendarOwnerId?`, `notes: [Note]`, `cancelled`.

**`Note`** (meeting summary): `docId`, `modifiedAt`, `text`, `sharedWith: [personId]`, `source?`, `sourceId?`.

**`Absence`**: `id`, `personId`, `start`, `end`, `type`, `source`, `enteredBy`, `createdAt`.

**`MeetingItem`** (card): see [Meeting card](../concepts/meeting-card.md) for every field. In short:
- `absenceId`, `absentPersonId`, `ownerRole`
- `event: EventRef`, `kind`, `ai: AiResult`, `status`
- `chosenAction`, `chosenProxyId`, `rescheduledTo`, `originalStart`
- `recommendedWhenDecided`, `aiWhenDecided`, `declinedProxyIds`, `decidedBy`
- reminder bookkeeping: `organizerAlerted`, `milestonesSent`, `inviteesAlerted`
- timestamps
- computed: `needsAttention`, `urgency`, `hoursToStart`

**`EventRef`**: the card's snapshot of the meeting: `calendarEventId`, `instanceStart`, `title`, `start`, `end`, `organizerId`, `attendees`.

**`AiResult`**: the card's AI block.

| Field | Meaning |
|---|---|
| `recommendation` | An `Action` |
| `reason` | One or two plain sentences |
| `confidence` | `high`, `medium` or `low` |
| `sources` | What was read: "previous summaries (N)", "invite title", "invite agenda", "proxy candidate list", "out-of-office check"… Filled in by code |
| `summariesAvailable` | Whether the viewer had any summaries |
| `suggestedProxyId`, `backupProxyId` | First and second choice |
| `kind` | The kind after the guard |
| `rulesAnswer` | `{kind, recommendation, suggestedProxyId, reason}`: what simple rules would have said |
| `needsHumanChoice` | A person must pick |
| `fingerprint` | `[{docId, modifiedAt}]` of the summaries used |
| `engine` | See [Recommendation pipeline](../architecture/recommendation-pipeline.md) |
| `model` | The Gemini model |
| `checks` | The guard's corrections, in plain words |
| `toolsUsed` | ADK tools called, in order |

**`ProxyRequest`**: `id`, `itemId`, `proxyId`, `requestedBy`, `note?`, `addedToMeeting`, `status`, `remindersSent`, `createdAt`, `respondedAt?`.

**`HistoryEvent`**: `id`, `itemId` (`"-"` for `meeting_scheduled`), `actorId` (a person or `"system"`), `type`, `detail` (technical), `at`, `text` (a plain sentence).

## Request bodies

| Model | Fields |
|---|---|
| `AbsenceCreate` | `personId`, `start`, `end` (the type is derived by the server) |
| `EventCreate` | `title`, `description`, `start`, `end`, `attendees` (UTC). The server refuses a start in the past and text over the `[input]` limits |
| `AttendeeAdd` | `personId`, `optional` |
| `ActionRequest` | `action`, `proxyId?`, `note?`, `noteFromAi`, `start?` (an organizer's picked time) |
| `MeetingActionRequest` | `action`, `start?` |
| `RespondRequest` | `response` (`accepted` / `declined`) |
| `NoteCreate` | `text`, `sharedWith` |
| `MeetLinkUpdate` | `meetUrl` |
| `TranscriptImportRequest` | `sharedWith` |
| `LeaveSystemRequest` | `personId`, `start`, `end` |

## Response shapes

| Model | Fields |
|---|---|
| `AttendeeItems` | `needsAction`, `noActionNeeded: NoActionGroups {teamCheckins, orgEvents, rescheduledOrCancelled}` |
| `OrganizerMeeting` | `calendarEventId`, `event`, `absentees: [MeetingItem]`, `ai`, `needsAttention`, `urgency?`, `hoursToStart?`, `done` |
| `MeResponse` | `person`, `counts: Counts {attendee, organizer, proxyRequests, attendeeOpen, organizerOpen, proxyOpen}` |
| `ProxyRequestView` | `request`, `item`, `notesAvailable` |
| `ProxyCandidate` | `personId`, `rank`, `reason`, `choice` (`first`/`second`)?, `declined` |
| `ProposedTime` | `proposedStart?`, `windowUsed` (`±1h`/`±2h`)?, `flagged`, `none` |
| `ScheduleResult` | `eventId`, `calendarProvider` (`google`/`demo`), `affected` |
| `AbsenceReport` | `absence`, `affected`, `needDecision` |
| `NoteDraftAvailable` | `available`, `reason?` |
| `NoteDraft` | `draft`, `engine` (`gemini`/`rules`/`rules_fallback`), `model?` |
| `MeetStatus` | `meetUrl?`, `configured`, `connected` |
| `Metrics` | `absencesSpotted`, `teamHoursAtRisk`, `handledAutomatically`, `meetingsWithPlan`, `meetingsAffected`, `avgNoticeDays`, `teamHoursSaved`, `recommendationsFollowedPct?`, `decisionsCounted`, `decisionsOnSchedule`, `daysWaitingAvoided`, `peopleSpared`, `estimateNote` |
| `Projection` | `rows: [ProjectionRow {employees, affectedMeetings, hoursSaved, value, decisionsOnSchedule, daysWaitingAvoided}]`, `measured`, `meetingsMeasured`, the rates and the assumptions |

## Id prefixes

Ids come from `Store.next_id(prefix)`:

| Prefix | Record |
|---|---|
| `a_` | absence |
| `i_` | card |
| `pr_` | proxy request |
| `h_` | history |
| `n_` | note |
| `evt_` | event scheduled in the app |

Seed ids are written by hand (`p_priya`, `evt_budget`). Imported Google events use `gcal:<hash>`.

## Related
- [Endpoints](endpoints.md)
- [Glossary](../overview/glossary.md)
