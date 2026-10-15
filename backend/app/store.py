"""Where the app's own data lives."""
from __future__ import annotations

from typing import Optional

from google.cloud import firestore

from .firestore import create_if_missing, decode_document, encode_model
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
    def get_meet_token(self, person_id: str) -> Optional[str]: ...
    def save_meet_token(self, person_id: str, encrypted_token: str) -> None: ...
    def delete_meet_token(self, person_id: str) -> None: ...
    def get_calendar_token(self, person_id: str) -> Optional[str]: ...
    def save_calendar_token(self, person_id: str, encrypted_token: str) -> None: ...
    def delete_calendar_token(self, person_id: str) -> None: ...


class InMemoryStore(Store):
    def __init__(self, people: list[Person]):
        self._people = {p.id: p for p in people}
        self._absences: dict[str, Absence] = {}
        self._items: dict[str, MeetingItem] = {}
        self._proxy: dict[str, ProxyRequest] = {}
        self._history: list[HistoryEvent] = []
        self._counters: dict[str, int] = {}
        self._meet_tokens: dict[str, str] = {}
        self._calendar_tokens: dict[str, str] = {}

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

    def get_meet_token(self, person_id):
        return self._meet_tokens.get(person_id)

    def save_meet_token(self, person_id, encrypted_token):
        self._meet_tokens[person_id] = encrypted_token

    def delete_meet_token(self, person_id):
        self._meet_tokens.pop(person_id, None)

    def get_calendar_token(self, person_id):
        return self._calendar_tokens.get(person_id)

    def save_calendar_token(self, person_id, encrypted_token):
        self._calendar_tokens[person_id] = encrypted_token

    def delete_calendar_token(self, person_id):
        self._calendar_tokens.pop(person_id, None)


class FirestoreStore(Store):
    """Firestore-backed app state. IDs in model records are document IDs."""

    def __init__(self, client: firestore.Client):
        self._client = client

    def _collection(self, name: str):
        return self._client.collection(name)

    def _all(self, collection: str, model_type):
        return [model_type.model_validate(doc.to_dict()) for doc in self._collection(collection).stream()]

    def people(self) -> list[Person]:
        return self._all("people", Person)

    def get_person(self, person_id: str) -> Optional[Person]:
        return decode_document(self._collection("people").document(person_id).get(), Person)

    def add_person_if_missing(self, person: Person) -> None:
        create_if_missing(self._collection("people").document(person.id), person)

    def add_absence(self, absence: Absence) -> None:
        self._collection("absences").document(absence.id).set(encode_model(absence))

    def absences(self) -> list[Absence]:
        return self._all("absences", Absence)

    def add_item(self, item: MeetingItem) -> None:
        self._collection("items").document(item.id).set(encode_model(item))

    def save_item(self, item: MeetingItem) -> None:
        self.add_item(item)

    def get_item(self, item_id: str) -> Optional[MeetingItem]:
        return decode_document(self._collection("items").document(item_id).get(), MeetingItem)

    def items(self) -> list[MeetingItem]:
        return self._all("items", MeetingItem)

    def add_proxy_request(self, req: ProxyRequest) -> None:
        self._collection("proxy_requests").document(req.id).set(encode_model(req))

    def save_proxy_request(self, req: ProxyRequest) -> None:
        self.add_proxy_request(req)

    def get_proxy_request(self, req_id: str) -> Optional[ProxyRequest]:
        return decode_document(self._collection("proxy_requests").document(req_id).get(), ProxyRequest)

    def proxy_requests(self) -> list[ProxyRequest]:
        return self._all("proxy_requests", ProxyRequest)

    def add_history(self, event: HistoryEvent) -> None:
        self._collection("history").document(event.id).set(encode_model(event))

    def history(self) -> list[HistoryEvent]:
        return self._all("history", HistoryEvent)

    def next_id(self, prefix: str) -> str:
        counter = self._collection("metadata").document("counters")

        @firestore.transactional
        def increment(transaction):
            snapshot = counter.get(transaction=transaction)
            data = snapshot.to_dict() if snapshot.exists else {}
            value = int(data.get(prefix, 0)) + 1
            data[prefix] = value
            transaction.set(counter, data)
            return value

        return f"{prefix}_{increment(self._client.transaction()):03d}"

    def get_meet_token(self, person_id: str) -> Optional[str]:
        snapshot = self._collection("meet_connections").document(person_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()["encryptedToken"]

    def save_meet_token(self, person_id: str, encrypted_token: str) -> None:
        self._collection("meet_connections").document(person_id).set({"encryptedToken": encrypted_token})

    def delete_meet_token(self, person_id: str) -> None:
        self._collection("meet_connections").document(person_id).delete()

    def get_calendar_token(self, person_id: str) -> Optional[str]:
        snapshot = self._collection("calendar_connections").document(person_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()["encryptedToken"]

    def save_calendar_token(self, person_id: str, encrypted_token: str) -> None:
        self._collection("calendar_connections").document(person_id).set({"encryptedToken": encrypted_token})

    def delete_calendar_token(self, person_id: str) -> None:
        self._collection("calendar_connections").document(person_id).delete()
