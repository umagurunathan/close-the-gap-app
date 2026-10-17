"""The per-request read cache ([store] request_cache): each request reads Firestore at most once per collection and
per document, sees its own writes, and never keeps anything for the next request."""
import pytest
from google.api_core.exceptions import AlreadyExists

from app.calendar import FirestoreCalendar
from app.firestore import begin_request_reads
from app.models import Absence, AbsenceSource, AbsenceType, Person
from app.store import FirestoreStore


class _Snapshot:
    def __init__(self, doc_id, data, reference=None):
        self.id, self._data, self.reference = doc_id, data, reference

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Document:
    def __init__(self, db, collection, doc_id):
        self._db, self._collection, self.id = db, collection, doc_id

    def get(self, transaction=None):
        self._db.reads += 1
        return _Snapshot(self.id, self._db.data.setdefault(self._collection, {}).get(self.id), self)

    def set(self, data):
        self._db.data.setdefault(self._collection, {})[self.id] = dict(data)

    def create(self, data):
        if self.id in self._db.data.setdefault(self._collection, {}):
            raise AlreadyExists("exists")
        self.set(data)

    def update(self, fields):
        self._db.data[self._collection][self.id].update(fields)

    def delete(self):
        self._db.data.setdefault(self._collection, {}).pop(self.id, None)


class _Query:
    def __init__(self, db, collection, workspace):
        self._db, self._collection, self._workspace = db, collection, workspace

    def stream(self):
        self._db.scans += 1
        docs = self._db.data.get(self._collection, {})
        return [_Snapshot(i, d, _Document(self._db, self._collection, i)) for i, d in sorted(docs.items())
                if d.get("workspaceId") == self._workspace]


class _Collection:
    def __init__(self, db, name):
        self._db, self._name = db, name

    def document(self, doc_id):
        return _Document(self._db, self._name, doc_id)

    def where(self, filter):
        return _Query(self._db, self._name, filter.value)


class _Batch:
    def __init__(self):
        self._deletes = []

    def delete(self, reference):
        self._deletes.append(reference)

    def commit(self):
        for reference in self._deletes:
            reference.delete()
        self._deletes = []


class FakeFirestore:
    def __init__(self):
        self.data, self.reads, self.scans = {}, 0, 0

    def collection(self, name):
        return _Collection(self, name)

    def batch(self):
        return _Batch()


@pytest.fixture
def db():
    yield FakeFirestore()
    begin_request_reads(False)   # leave no cache behind for other tests


def _person(pid, name):
    return Person(id=pid, name=name, email=f"{pid}@example.com", title="Engineer", department="Platform")


def test_one_request_reads_each_collection_once_and_sees_its_own_writes(db):
    store = FirestoreStore(db, "guest")
    store.save_person(_person("p_a", "Asha"))
    begin_request_reads(True)

    assert [p.name for p in store.people()] == ["Asha"]
    store.people()
    store.get_person("p_a")
    assert db.scans == 1 and db.reads == 0     # the second list and the single read came from the first scan

    store.save_person(_person("p_b", "Bala"))
    assert [p.name for p in store.people()] == ["Asha", "Bala"]
    assert store.get_person("p_b").name == "Bala"
    assert db.scans == 1


def test_a_new_request_reads_again_and_sees_changes_made_elsewhere(db):
    store = FirestoreStore(db, "guest")
    store.save_person(_person("p_a", "Asha"))
    begin_request_reads(True)
    assert store.get_person("p_a").name == "Asha"

    other_backend = FirestoreStore(db, "guest")   # for example the live and a local backend on one database
    begin_request_reads(False)
    other_backend.save_person(_person("p_a", "Asha R"))

    begin_request_reads(True)                    # the next request
    assert store.get_person("p_a").name == "Asha R"


def test_objects_handed_out_are_copies(db):
    store = FirestoreStore(db, "guest")
    store.save_person(_person("p_a", "Asha"))
    begin_request_reads(True)
    store.get_person("p_a").name = "changed but not saved"
    assert store.get_person("p_a").name == "Asha"


def test_deleting_and_missing_documents(db):
    store = FirestoreStore(db, "guest")
    begin_request_reads(True)
    assert store.get_person("p_x") is None
    store.add_absence(Absence(id="abs_1", personId="p_a", start="2026-11-17", end="2026-11-17",
                              type=AbsenceType.planned, source=AbsenceSource.manual, enteredBy="p_a",
                              createdAt="2026-11-08T09:00:00Z"))
    assert [a.id for a in store.absences()] == ["abs_1"]
    assert store.delete_where("absences", lambda rid, d: True) == ["abs_1"]
    assert store.absences() == []
    store.add_person_if_missing(_person("p_x", "Xavier"))
    assert store.get_person("p_x").name == "Xavier"


def test_the_two_areas_never_share_what_they_read(db):
    guest, company = FirestoreStore(db, "guest"), FirestoreStore(db, "company")
    begin_request_reads(True)
    guest.save_person(_person("p_a", "Demo Asha"))
    assert company.get_person("p_a") is None and company.people() == []
    assert [p.name for p in guest.people()] == ["Demo Asha"]


def test_the_calendar_and_the_store_agree_on_deleted_events(db):
    from datetime import datetime, timezone
    from app.models import CalEvent
    store, calendar = FirestoreStore(db, "guest"), FirestoreCalendar(db, "guest")
    begin_request_reads(True)
    start = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
    calendar.save_event(CalEvent(id="evt_1", title="Sync", organizerId="p_a", start=start, end=start,
                                    attendees=[]))
    assert [e.id for e in calendar.all_events()] == ["evt_1"]
    store.delete_where("events", lambda rid, d: True)    # how Reset demo data removes meetings
    assert calendar.all_events() == [] and calendar.get("evt_1") is None


def test_switched_off_every_call_reads_firestore(db):
    store = FirestoreStore(db, "guest")
    store.save_person(_person("p_a", "Asha"))
    begin_request_reads(False)
    store.people(), store.people(), store.get_person("p_a")
    assert db.scans == 2 and db.reads == 1
