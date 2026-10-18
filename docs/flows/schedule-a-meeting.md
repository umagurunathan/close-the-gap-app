---
type: Flow
title: "Flow: a meeting is scheduled, changed or synced while someone is out"
description: The reverse direction of the absence scan; POST /events (Google first, rollback), adding an attendee, and Calendar sync all run _scan_event and alert the organizer once.
resource: ../../backend/app/service.py
tags: [flow, scheduling, calendar, scan]
sources:
  - resource: ../../backend/app/main.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/google_calendar.py
  - resource: ../../web/src/components/ScheduleMeeting.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Flow: a meeting is scheduled while someone is out

Close the Gap works in both directions. When a meeting is **scheduled, gains an attendee, or arrives through a Calendar sync** on a day a key person is already out, the same card flow starts at once.

## Schedule a meeting (`POST /events`)

1. **The form** (`ScheduleMeeting.jsx`):
   - title (required, up to 150 characters), agenda ("the AI reads it", up to 3,000), date (today or later), start time (IST), duration;
   - invitees, searched client-side by name, email or title, each marked Required or Optional.
   - The body is `{title, description, start, end, attendees: [{personId, optional}]}`, with times in UTC.
2. **`main.post_event`** checks that `end > start` and that the attendees exist.
   - **If the organizer's Google Calendar is connected**, it creates the Google event first (`calendar.create_event`, `sendUpdates=all`), so Google sends the invitations.
   - If the app then fails with a lookup, value or permission error, the Google event is **deleted again** (rollback).
3. **`Service.schedule_meeting`**:
   - validates: the start must be in the future ("Please choose a start time in the future.") and the title and agenda within the `[input]` limits;
   - creates a `CalEvent` (`evt_…`; the title defaults to "Untitled meeting"). With a Google id, it sets `googleCalendarOwnerId = organizer`;
   - logs `meeting_scheduled`;
   - calls `_scan_event`.
4. **`_scan_event(e)`**: for the organizer and every **required** invitee, it looks for an absence covering `e.start.date()`.
   - Each one gets `_create_item`, the same as in [Report an absence](report-an-absence.md).
   - **Optional invitees never trigger anything.**
   - In a large event, ordinary attendees get a quiet `org_event` card.
5. **One email to the organizer** for all absent key people: "You scheduled '{title}' while X and Y are out". Those cards are marked `organizerAlerted`, so the under-24-hour alert does not repeat it.
6. **Response** (`ScheduleResult`): `{eventId, calendarProvider: "google"|"demo", affected: [cards]}`. If someone is out, the web app jumps to **Organizer Mode** on the new card.

## Add someone to an existing meeting (`POST /events/{id}/attendees`)

`Service.add_attendee`:
- the caller must be the organizer, and the person must not already be invited;
- for a Google event the organizer's calendar must be connected, and Google is updated first;
- then `_scan_event(e, only=[person])`, so only the new person is checked.

## Google Calendar sync (`POST /integrations/google-calendar/sync`)

The sync imports or updates the signed-in person's meetings from 30 days back to a year ahead. **Every imported or updated event goes through `_scan_event`.** A meeting created directly in Google on a day someone is out therefore produces cards too. Full rules: [Google integrations](../architecture/google-integrations.md).

## Tests

- `scheduling_a_meeting_while_a_key_person_is_out_alerts_the_organizer`
- `optional_attendees_and_people_who_are_in_do_not_trigger_it`
- `several_key_people_out_means_one_email`
- `adding_someone_to_an_existing_meeting_runs_the_same_check`
- `a_meeting_scheduled_in_the_app_is_not_imported_twice_by_the_calendar_sync`

## Related
- [Key people](../concepts/key-people.md)
- [Google integrations](../architecture/google-integrations.md)
