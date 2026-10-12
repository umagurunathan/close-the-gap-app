"""Builds the demo world: people, calendar events and starting absences, from seed/seed.json."""
from __future__ import annotations

import json
from pathlib import Path

from . import config, notify
from .calendar import SimCalendar
from .models import AbsenceSource, CalEvent, Person
from .service import Service
from .store import InMemoryStore

BACKEND_DIR = Path(__file__).resolve().parent.parent


def build_service() -> Service:
    path = Path(config.seed_path())
    if not path.is_absolute():
        path = BACKEND_DIR / path
    data = json.loads(path.read_text(encoding="utf-8-sig"))  # utf-8-sig also accepts a leading BOM from Windows editors
    if config.store_kind() != "memory":
        raise NotImplementedError("Only STORE=memory exists so far; add FirestoreStore, then switch here.")
    store = InMemoryStore([Person(**p) for p in data["people"]])
    calendar = SimCalendar([CalEvent(**e) for e in data["events"]])
    svc = Service(store, calendar)
    for a in data["absences"]:
        # the type (planned / sudden) is worked out from the notice, so seed.json doesn't need to say
        svc.create_absence(a["personId"], _d(a["start"]), _d(a["end"]), AbsenceSource(a["source"]), a["enteredBy"])
    notify.clear()  # don't show the seeding emails as if they were live
    return svc


def _d(s: str):
    from datetime import date
    return date.fromisoformat(s)
