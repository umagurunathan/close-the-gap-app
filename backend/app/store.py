"""Where the app's own data lives.

`Store` is the interface the rest of the code uses. Today there is only the in-memory version
(data is reset when the server restarts, which is fine for development). For Cloud Run we add a
`FirestoreStore` with the same methods and pick it with STORE=firestore. Nothing else changes.
"""
from __future__ import annotations

from typing import Optional

from .models import Absence, HistoryEvent, MeetingItem, Person, ProxyRequest


class Store:
    """Interface (documentation of what any store must offer)."""

    def people(self) -> list[Person]: ...
    def get_person(self, person_id: str) -> Optional[Person]: ...
    def add_absence(self, absence: Absence) -> None: ...
    def absences(self) -> list[Absence]: ...
    def add_item(self, item: MeetingItem) -> None: ...
    def save_item(self, item: MeetingItem) -> None: ...
    def get_item(self, item_id: str) -> Optional[MeetingItem]: ...
    def items(self) -> list[MeetingItem]: ...
    def add_proxy_request(self, req: ProxyRequest) -> None: ...
    def save_proxy_request(self, req: ProxyRequest) -> None: ...
    def get_proxy_request(self, req_id: str) -> Optional[ProxyRequest]: ...
    def proxy_requests(self) -> list[ProxyRequest]: ...
    def add_history(self, event: HistoryEvent) -> None: ...
    def history(self) -> list[HistoryEvent]: ...
    def next_id(self, prefix: str) -> str: ...


class InMemoryStore(Store):
    def __init__(self, people: list[Person]):
        self._people = {p.id: p for p in people}
        self._absences: dict[str, Absence] = {}
        self._items: dict[str, MeetingItem] = {}
        self._proxy: dict[str, ProxyRequest] = {}
        self._history: list[HistoryEvent] = []
        self._counters: dict[str, int] = {}

    def people(self):
        return list(self._people.values())

    def get_person(self, person_id):
        return self._people.get(person_id)

    def add_absence(self, absence):
        self._absences[absence.id] = absence

    def absences(self):
        return list(self._absences.values())

    def add_item(self, item):
        self._items[item.id] = item

    def save_item(self, item):
        self._items[item.id] = item

    def get_item(self, item_id):
        return self._items.get(item_id)

    def items(self):
        return list(self._items.values())

    def add_proxy_request(self, req):
        self._proxy[req.id] = req

    def save_proxy_request(self, req):
        self._proxy[req.id] = req

    def get_proxy_request(self, req_id):
        return self._proxy.get(req_id)

    def proxy_requests(self):
        return list(self._proxy.values())

    def add_history(self, event):
        self._history.append(event)

    def history(self):
        return list(self._history)

    def next_id(self, prefix):
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_{self._counters[prefix]:03d}"
