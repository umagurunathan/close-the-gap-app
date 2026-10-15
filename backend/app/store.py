"""Where the app's own data lives."""
from __future__ import annotations

from typing import Optional

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from .firestore import encode_model
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

    def __init__(self, client: firestore.Client, workspace_id: str = "company"):
        self._client = client
        self._workspace_id = workspace_id

    def _collection(self, name: str):
        return self._client.collection(name)

    def _document(self, collection: str, document_id: str):
        return self._collection(collection).document(f"{self._workspace_id}__{document_id}")

    def _encode(self, model) -> dict:
        data = encode_model(model)
        data["workspaceId"] = self._workspace_id
        return data

    def _decode(self, snapshot, model_type):
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        data.pop("workspaceId", None)
        return model_type.model_validate(data)

    def _all(self, collection: str, model_type):
        return [
            model_type.model_validate({key: value for key, value in doc.to_dict().items()
                                       if key != "workspaceId"})
            for doc in self._collection(collection).where(
                filter=FieldFilter("workspaceId", "==", self._workspace_id)
            ).stream()
        ]

    def people(self) -> list[Person]:
        return self._all("people", Person)

    def get_person(self, person_id: str) -> Optional[Person]:
        return self._decode(self._document("people", person_id).get(), Person)

    def add_person_if_missing(self, person: Person) -> None:
        reference = self._document("people", person.id)
        try:
            reference.create(self._encode(person))
        except AlreadyExists:
            pass

    def ensure_guest_person(self, person: Person) -> None:
        reference = self._document("people", person.id)
        snapshot = reference.get()
        if not snapshot.exists:
            try:
                reference.create(self._encode(person))
            except AlreadyExists:
                pass
            return
        if (snapshot.to_dict() or {}).get("email") != person.email:
            reference.update({"email": person.email})

    def add_absence(self, absence: Absence) -> None:
        self._document("absences", absence.id).set(self._encode(absence))

    def absences(self) -> list[Absence]:
        return self._all("absences", Absence)

    def add_item(self, item: MeetingItem) -> None:
        self._document("items", item.id).set(self._encode(item))

    def save_item(self, item: MeetingItem) -> None:
        self.add_item(item)

    def get_item(self, item_id: str) -> Optional[MeetingItem]:
        return self._decode(self._document("items", item_id).get(), MeetingItem)

    def items(self) -> list[MeetingItem]:
        return self._all("items", MeetingItem)

    def add_proxy_request(self, req: ProxyRequest) -> None:
        self._document("proxy_requests", req.id).set(self._encode(req))

    def save_proxy_request(self, req: ProxyRequest) -> None:
        self.add_proxy_request(req)

    def get_proxy_request(self, req_id: str) -> Optional[ProxyRequest]:
        return self._decode(self._document("proxy_requests", req_id).get(), ProxyRequest)

    def proxy_requests(self) -> list[ProxyRequest]:
        return self._all("proxy_requests", ProxyRequest)

    def add_history(self, event: HistoryEvent) -> None:
        self._document("history", event.id).set(self._encode(event))

    def history(self) -> list[HistoryEvent]:
        return self._all("history", HistoryEvent)

    def next_id(self, prefix: str) -> str:
        counter = self._document("metadata", "counters")

        @firestore.transactional
        def increment(transaction):
            snapshot = counter.get(transaction=transaction)
            data = snapshot.to_dict() if snapshot.exists else {}
            value = int(data.get(prefix, 0)) + 1
            data[prefix] = value
            data["workspaceId"] = self._workspace_id
            transaction.set(counter, data)
            return value

        return f"{prefix}_{increment(self._client.transaction()):03d}"

    def get_meet_token(self, person_id: str) -> Optional[str]:
        snapshot = self._document("meet_connections", person_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()["encryptedToken"]

    def save_meet_token(self, person_id: str, encrypted_token: str) -> None:
        self._document("meet_connections", person_id).set(
            {"encryptedToken": encrypted_token, "workspaceId": self._workspace_id})

    def delete_meet_token(self, person_id: str) -> None:
        self._document("meet_connections", person_id).delete()

    def get_calendar_token(self, person_id: str) -> Optional[str]:
        snapshot = self._document("calendar_connections", person_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()["encryptedToken"]

    def save_calendar_token(self, person_id: str, encrypted_token: str) -> None:
        self._document("calendar_connections", person_id).set(
            {"encryptedToken": encrypted_token, "workspaceId": self._workspace_id})

    def delete_calendar_token(self, person_id: str) -> None:
        self._document("calendar_connections", person_id).delete()
