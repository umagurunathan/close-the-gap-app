"""Simulated calendar. This is the "calendar adapter": the rest of the app only talks to
these methods. Later a GoogleCalendar class with the same methods can replace it for the recorded demo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from .firestore import RequestReads, encode_model
from .models import CalEvent, Note


class SimCalendar:
    def __init__(self, events: list[CalEvent]):
        self._events = {e.id: e for e in events}

    # ---- reads ----
    def get(self, event_id: str) -> Optional[CalEvent]:
        return self._events.get(event_id)

    def all_events(self) -> list[CalEvent]:
        return list(self._events.values())

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

    def remove_event(self, event_id: str) -> None:
        self._events.pop(event_id, None)

    def save_event(self, event: CalEvent) -> CalEvent:
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


class FirestoreCalendar:
    """Firestore-backed calendar records, including their shared meeting notes."""

    def __init__(self, client: firestore.Client, workspace_id: str = "company"):
        self._events = client.collection("events")
        self._workspace_id = workspace_id
        self._reads = RequestReads(workspace_id)

    def _document(self, event_id: str):
        return self._events.document(f"{self._workspace_id}__{event_id}")

    @staticmethod
    def _model(data: Optional[dict]) -> Optional[CalEvent]:
        if data is None:
            return None
        return CalEvent.model_validate({key: value for key, value in data.items() if key != "workspaceId"})

    def _query(self):
        return self._events.where(filter=FieldFilter("workspaceId", "==", self._workspace_id))

    def get(self, event_id: str) -> Optional[CalEvent]:
        reference = self._document(event_id)
        return self._model(self._reads.get("events", reference.id, reference.get, lambda: self._query().stream()))

    def all_events(self) -> list[CalEvent]:
        return [self._model(data) for data in self._reads.scan("events", self._query().stream)]

    def add_event(self, event: CalEvent) -> CalEvent:
        self.save_event(event)
        return event

    def remove_event(self, event_id: str) -> None:
        reference = self._document(event_id)
        reference.delete()
        self._reads.wrote("events", reference.id, None)

    def add_event_if_missing(self, event: CalEvent) -> bool:
        reference = self._document(event.id)
        data = {**encode_model(event), "workspaceId": self._workspace_id}
        try:
            reference.create(data)
        except AlreadyExists:
            self._reads.forget("events", reference.id)
            return False
        self._reads.wrote("events", reference.id, data)
        return True

    def save_event(self, event: CalEvent) -> CalEvent:
        reference = self._document(event.id)
        data = {**encode_model(event), "workspaceId": self._workspace_id}
        reference.set(data)
        self._reads.wrote("events", reference.id, data)
        return event

    def involving(self, person_id: str) -> list[CalEvent]:
        return sorted(
            [event for event in self.all_events()
             if not event.cancelled and (event.organizerId == person_id
                                         or any(a.personId == person_id for a in event.attendees))],
            key=lambda event: event.start,
        )

    def events_in_window(self, person_id: str, start: date, end: date) -> list[CalEvent]:
        return [event for event in self.involving(person_id) if start <= event.start.date() <= end]

    def busy(self, person_id: str, ignore_event_id: Optional[str] = None) -> list[tuple[datetime, datetime]]:
        return [(event.start, event.end) for event in self.involving(person_id) if event.id != ignore_event_id]

    def visible_notes(self, event: CalEvent, viewer_id: str) -> list[Note]:
        if viewer_id == event.organizerId:
            return list(event.notes)
        return [note for note in event.notes if viewer_id in note.sharedWith]

    def move_event(self, event_id: str, new_start: datetime) -> CalEvent:
        event = self.get(event_id)
        if event is None:
            raise KeyError(event_id)
        duration = event.end - event.start
        event.start = new_start
        event.end = new_start + duration
        return self.save_event(event)

    def cancel_event(self, event_id: str) -> CalEvent:
        event = self.get(event_id)
        if event is None:
            raise KeyError(event_id)
        event.cancelled = True
        return self.save_event(event)


def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_minutes(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)
