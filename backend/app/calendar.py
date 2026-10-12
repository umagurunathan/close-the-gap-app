"""Simulated calendar. This is the "calendar adapter": the rest of the app only talks to
these methods. Later a GoogleCalendar class with the same methods can replace it for the recorded demo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .models import CalEvent, Note


class SimCalendar:
    def __init__(self, events: list[CalEvent]):
        self._events = {e.id: e for e in events}

    # ---- reads ----
    def get(self, event_id: str) -> Optional[CalEvent]:
        return self._events.get(event_id)

    def involving(self, person_id: str) -> list[CalEvent]:
        """Events where the person is the organizer or an attendee (not cancelled)."""
        out = []
        for e in self._events.values():
            if e.cancelled:
                continue
            if e.organizerId == person_id or any(a.personId == person_id for a in e.attendees):
                out.append(e)
        return sorted(out, key=lambda e: e.start)

    def events_in_window(self, person_id: str, start: date, end: date) -> list[CalEvent]:
        """Events involving the person that fall on any day from `start` to `end` inclusive (UTC dates)."""
        return [e for e in self.involving(person_id) if start <= e.start.date() <= end]

    def busy(self, person_id: str, ignore_event_id: Optional[str] = None) -> list[tuple[datetime, datetime]]:
        return [(e.start, e.end) for e in self.involving(person_id) if e.id != ignore_event_id]

    def visible_notes(self, event: CalEvent, viewer_id: str) -> list[Note]:
        """Only notes the viewer is allowed to open: shared with them, or they are the organizer."""
        if viewer_id == event.organizerId:
            return list(event.notes)
        return [n for n in event.notes if viewer_id in n.sharedWith]

    # ---- writes (only the organizer's actions call these) ----
    def add_event(self, event: CalEvent) -> CalEvent:
        self._events[event.id] = event
        return event

    def move_event(self, event_id: str, new_start: datetime) -> CalEvent:
        e = self._events[event_id]
        duration = e.end - e.start
        e.start = new_start
        e.end = new_start + duration
        return e

    def cancel_event(self, event_id: str) -> CalEvent:
        e = self._events[event_id]
        e.cancelled = True
        return e


def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_minutes(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)
