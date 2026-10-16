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
    data = _load_seed()
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
        workspace_id = config.firestore_workspace_id()
        store = FirestoreStore(client, workspace_id)
        calendar = FirestoreCalendar(client, workspace_id)
        new_events = []
        for person in people:
            if workspace_id == "guest":
                person.email = f"{person.id}@example.invalid"
                store.ensure_guest_person(person)
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


def reset_demo(svc: Service) -> Service:
    """The "Reset demo data" button. The demo people are everyone in seed.json; they and their meetings go back to
    the seed (including the replayed past week), with an empty AI cache. Anyone else (real people who signed in with
    their own account) and their meetings are not touched."""
    google_calendar = svc.google_calendar
    if not isinstance(svc.store, FirestoreStore):
        build_service(into=svc, mode="memory")
        svc.google_calendar = google_calendar
        return svc
    data = _load_seed()
    demo = {p["id"] for p in data["people"]}
    seed_events = {e["id"] for e in data["events"]}
    store, calendar = svc.store, svc.calendar
    svc.wait_for_analysis(cancel=True)
    # 1. Everything linked to a demo person: their meetings (from the seed, created in the app, or imported from a
    #    Google Calendar), cards, absences, proxy requests, history and calendar connections.
    events = set(store.delete_where("events", lambda rid, d: rid in seed_events or d.get("organizerId") in demo
                                    or d.get("googleCalendarOwnerId") in demo))
    items = set(store.delete_where("items", lambda rid, d: d.get("absentPersonId") in demo
                                   or (d.get("event") or {}).get("calendarEventId") in events))
    store.delete_where("absences", lambda rid, d: d.get("personId") in demo)
    store.delete_where("proxy_requests", lambda rid, d: d.get("itemId") in items or d.get("proxyId") in demo
                       or d.get("requestedBy") in demo)
    store.delete_where("history", lambda rid, d: d.get("itemId") in items or d.get("actorId") in demo)
    for collection in ("calendar_connections", "meet_connections"):
        store.delete_where(collection, lambda rid, d: rid in demo)
    # 2. The seed again: people (with their demo emails), meetings, the past week, then today's absences.
    for p in data["people"]:
        store.save_person(Person(**p))
    for e in data["events"]:
        calendar.save_event(CalEvent(**e))
    svc.__init__(store, calendar, google_calendar)
    _replay_past_week(svc, data.get("pastWeek"))
    for a in data["absences"]:
        svc.create_absence(a["personId"], _d(a["start"]), _d(a["end"]), AbsenceSource(a["source"]), a["enteredBy"])
    notify.clear()
    return svc


def _load_seed() -> dict:
    path = Path(config.seed_path())
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return json.loads(path.read_text(encoding="utf-8-sig"))  # utf-8-sig also accepts a leading BOM from Windows editors


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
