---
type: Architecture Component
title: Reschedule search
description: The deterministic slot search (same time of day, ±1 h then ±2 h, next 7 working days, every key person back and free), the organizer's picked-time check, and the move-Google-first rule.
resource: ../../backend/app/scheduling.py
tags: [scheduling, reschedule, algorithm, plain-code]
sources:
  - resource: ../../backend/app/scheduling.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/roles.py
  - resource: ../../backend/config/settings.toml
  - resource: ../../web/src/components/ReschedulePanel.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Reschedule search

Rescheduling is **plain deterministic code, not AI** (`app/scheduling.find_slot`). It proposes **one** time. The organizer takes it in one click ("Reschedule to Mon, 23 Nov · 3:00 pm IST") or picks another time.

## Algorithm (`find_slot(event, calendar, absences, now, people)`)

1. The meeting keeps its duration and its **original time of day**.
2. The people who must be free are `roles.key_people(event, people)`: the organizer plus required invitees, or only hosts in a large event.
3. For each window, first `[reschedule] preferred_window_hours` (±1 h) and then `wider_window_hours` (±2 h):
   - Walk forward day by day from the day after the original. Skip weekends if `skip_weekends`. Check up to `max_working_days` (7) working days.
   - Skip a day when any key person is on leave.
   - Try offsets in order of closeness: 0, +30, −30, +60, −60 … minutes (`step_minutes` = 30).
   - Skip candidate times that are not in the future.
   - Return the first time when **every key person is free** (`calendar.busy`, ignoring this meeting).
4. A time found in the wider window is `flagged`, which the UI shows as "a little off the original time of day".
5. If nothing fits: `ProposedTime(none=True)`.

`GET /items/{id}/proposed-time` returns `{proposedStart, windowUsed ("±1h"/"±2h"), flagged, none}`.

**Simplifications:**
- Times are handled in UTC, so the clock time of a meeting is preserved in UTC.
- "Free" means no overlapping meeting **known to the app**. There is no live Google free/busy query.

## The organizer's own time (`Service._check_picked_time`)

The organizer can always pick a time, including when none was found. The time must be:
- in the future;
- different from the current start;
- on a day when every key person, and everyone whose card this is, is **back**.

Whether people are busy at that hour is the organizer's call; Google Calendar tells the guests.

## Applying it

- **One card** (`apply_action(..., reschedule, start=None|picked)`):
  - a non-organizer gets `awaiting_organizer`;
  - an organizer with no time found gets `no_slot_found`;
  - otherwise `_move_meeting` runs and the card becomes `rescheduled`, with `originalStart` and `rescheduledTo` set.
- **Whole meeting** (`apply_meeting_action`): **one move for everyone**. Every open card becomes `rescheduled`, and open proxy requests are withdrawn.
- **`_move_meeting`: Google first.** For a Google event the organizer's calendar must be the connected one. The event is PATCHed with `sendUpdates=all`, so Google tells the guests, and only then is the app's copy moved. **If Google refuses, nothing in the app changes.**
- A later Calendar sync that finds the meeting at another time updates `rescheduledTo`: "Google's time wins".

## Tests

- `reschedule_keeps_time_of_day_and_avoids_leave`
- `meeting_level_reschedule_moves_once_and_settles_everyone`
- `the_organizer_reschedule_moves_the_google_event_once`
- `if_google_refuses_the_move_nothing_changes`
- `the_organizer_can_pick_another_time`
- `a_picked_time_is_checked`
- `the_organizer_can_still_reschedule_when_no_time_is_found`
- `a_sync_after_a_reschedule_follows_google`

## Related
- [Actions](../concepts/actions.md)
- [Key people](../concepts/key-people.md)
- [Google integrations](google-integrations.md)
