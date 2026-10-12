"""Reschedule search: plain deterministic code, not an AI agent.

Rules:
- Same time of day as the original meeting, within +/-1 hour; if nothing is found, widen to +/-2 hours.
- Look across the next several working days and pick the earliest day that works.
- Every key person (the organizer + all required attendees) must be free and not on leave.
- Never pick a time that excludes a required attendee.

Simplification: times are handled in UTC. A real version would use each meeting's own time zone.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from .calendar import SimCalendar
from .models import Absence, CalEvent, ProposedTime

STEP_MINUTES = 30
MAX_WORKING_DAYS = 7


def key_people(event: CalEvent) -> list[str]:
    ids = [event.organizerId] + [a.personId for a in event.attendees if not a.optional]
    return list(dict.fromkeys(ids))


def _on_leave(person_id: str, day, absences: list[Absence]) -> bool:
    return any(a.personId == person_id and a.start <= day <= a.end for a in absences)


def _is_free(person_id: str, start: datetime, end: datetime, calendar: SimCalendar, ignore_event_id: str) -> bool:
    return all(not (start < b_end and end > b_start) for b_start, b_end in calendar.busy(person_id, ignore_event_id))


def find_slot(
    event: CalEvent,
    calendar: SimCalendar,
    absences: list[Absence],
    now: datetime,
    max_working_days: int = MAX_WORKING_DAYS,
) -> ProposedTime:
    duration = event.end - event.start
    people = key_people(event)
    original_tod = event.start.timetz()

    for window_hours in (1, 2):
        offsets = _offsets_by_closeness(window_hours)
        day = event.start.date()
        checked = 0
        while checked < max_working_days:
            day += timedelta(days=1)
            if day.weekday() >= 5:  # skip Sat/Sun
                continue
            checked += 1
            center = datetime.combine(day, time(original_tod.hour, original_tod.minute), tzinfo=event.start.tzinfo)
            if any(_on_leave(p, day, absences) for p in people):
                continue
            for off in offsets:
                start = center + timedelta(minutes=off)
                end = start + duration
                if start <= now:
                    continue
                if all(_is_free(p, start, end, calendar, event.id) for p in people):
                    return ProposedTime(
                        proposedStart=start,
                        windowUsed=f"±{window_hours}h",
                        flagged=window_hours > 1,
                    )
    return ProposedTime(none=True)


def _offsets_by_closeness(window_hours: int) -> list[int]:
    """0, +30, -30, +60, -60, ... so the time closest to the original is tried first."""
    out = [0]
    for m in range(STEP_MINUTES, window_hours * 60 + 1, STEP_MINUTES):
        out.extend([m, -m])
    return out
