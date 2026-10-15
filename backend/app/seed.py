"""Builds the demo world: people, calendar events and starting absences, from seed/seed.json."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import config, notify
from .calendar import FirestoreCalendar, SimCalendar
from .firestore import new_client
from .models import AbsenceSource, Action, CalEvent, Person, ProxyRequestStatus
from .service import Service
from .store import FirestoreStore, InMemoryStore

BACKEND_DIR = Path(__file__).resolve().parent.parent


def build_service(into: Optional[Service] = None, mode: Optional[str] = None) -> Service:
    """A fresh demo world. With `into`, the existing service is reset in place (the "Reset demo" button): same object,
    so the running app keeps using it, but new data and an empty AI cache, so the AI analyses everything again."""
    path = Path(config.seed_path())
    if not path.is_absolute():
        path = BACKEND_DIR / path
    data = json.loads(path.read_text(encoding="utf-8-sig"))  # utf-8-sig also accepts a leading BOM from Windows editors
    people = [Person(**p) for p in data["people"]]
    events = [CalEvent(**e) for e in data["events"]]
    kind = (mode or config.store_kind()).strip().lower()
    if kind == "memory":
        store = InMemoryStore(people)
        calendar = SimCalendar(events)
        if into is None:
            svc = Service(store, calendar)
        else:
            into.wait_for_analysis(cancel=True)
            into.__init__(store, calendar)
            svc = into
        _replay_past_week(svc, data.get("pastWeek"))
        for absence_data in data["absences"]:
            svc.create_absence(absence_data["personId"], _d(absence_data["start"]), _d(absence_data["end"]),
                               AbsenceSource(absence_data["source"]), absence_data["enteredBy"])
    elif kind == "firestore":
        client = new_client(config.firestore_project(), config.firestore_database())
        collection_prefix = config.firestore_collection_prefix()
        store = FirestoreStore(client, collection_prefix)
        calendar = FirestoreCalendar(client, collection_prefix)
        new_events = []
        for person in people:
            if collection_prefix:
                person.email = f"{person.id}@example.invalid"
                store.ensure_public_demo_person(person)
            else:
                store.add_person_if_missing(person)
        for event in events:
            if calendar.add_event_if_missing(event):
                new_events.append(event)
        svc = Service(store, calendar)
        for absence_data in data["absences"]:
            start, end = _d(absence_data["start"]), _d(absence_data["end"])
            source = AbsenceSource(absence_data["source"])
            existing = next((absence for absence in store.absences()
                             if absence.personId == absence_data["personId"] and absence.start == start
                             and absence.end == end and absence.source == source), None)
            if existing is None:
                svc.create_absence(absence_data["personId"], start, end, source, absence_data["enteredBy"])
            elif any(start <= event.start.date() <= end and
                     (event.organizerId == existing.personId or
                      any(attendee.personId == existing.personId for attendee in event.attendees))
                     for event in new_events):
                svc._scan(existing)
    else:
        raise ValueError(f"Unsupported STORE={kind!r}; expected 'memory' or 'firestore'")
    notify.clear()  # don't show the seeding emails as if they were live
    return svc


def _replay_past_week(svc: Service, past: Optional[dict]) -> None:
    """Absences from a past week and what people did about them, replayed with the clock set back, so the impact
    numbers and the Past tab start with real, handled examples instead of zeros. No AI is asked for these."""
    if not past:
        return
    when = datetime.fromisoformat(past["now"].replace("Z", "+00:00"))
    svc.now = lambda: when          # this object only; the class method is restored below
    svc.replaying = True            # no background AI for replayed cards
    try:
        for a in past["absences"]:
            svc.create_absence(a["personId"], _d(a["start"]), _d(a["end"]), AbsenceSource(a["source"]), a["enteredBy"])
        for act in past["actions"]:
            item = next(i for i in svc.store.items()
                        if i.event.calendarEventId == act["eventId"] and i.absentPersonId == act["absent"])
            svc.apply_action(item.id, act["by"], Action(act["action"]), act.get("proxyId"))
            if act.get("accept"):
                req = next(r for r in svc.store.proxy_requests()
                           if r.itemId == item.id and r.status == ProxyRequestStatus.pending)
                svc.respond_proxy(req.id, req.proxyId, ProxyRequestStatus.accepted)
    finally:
        del svc.now
        svc.replaying = False


def _d(s: str) -> date:
    return date.fromisoformat(s)
