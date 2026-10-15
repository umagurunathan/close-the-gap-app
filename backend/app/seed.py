"""Builds the demo world: people, calendar events and starting absences, from seed/seed.json."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import config, notify
from .calendar import SimCalendar
from .models import AbsenceSource, Action, CalEvent, Person, ProxyRequestStatus
from .service import Service
from .store import InMemoryStore

BACKEND_DIR = Path(__file__).resolve().parent.parent


def build_service(into: Optional[Service] = None) -> Service:
    """A fresh demo world. With `into`, the existing service is reset in place (the "Reset demo" button): same object,
    so the running app keeps using it, but new data and an empty AI cache, so the AI analyses everything again."""
    path = Path(config.seed_path())
    if not path.is_absolute():
        path = BACKEND_DIR / path
    data = json.loads(path.read_text(encoding="utf-8-sig"))  # utf-8-sig also accepts a leading BOM from Windows editors
    if config.store_kind() != "memory":
        raise NotImplementedError("Only STORE=memory exists so far; add FirestoreStore, then switch here.")
    store = InMemoryStore([Person(**p) for p in data["people"]])
    calendar = SimCalendar([CalEvent(**e) for e in data["events"]])
    if into is None:
        svc = Service(store, calendar)
    else:
        into.wait_for_analysis(cancel=True)
        into.__init__(store, calendar)
        svc = into
    _replay_past_week(svc, data.get("pastWeek"))
    for a in data["absences"]:
        # the type (planned / sudden) is worked out from the notice, so seed.json doesn't need to say
        svc.create_absence(a["personId"], _d(a["start"]), _d(a["end"]), AbsenceSource(a["source"]), a["enteredBy"])
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
