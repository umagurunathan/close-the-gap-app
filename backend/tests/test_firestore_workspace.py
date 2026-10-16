from unittest.mock import Mock

import pytest

from app import config
from app.calendar import FirestoreCalendar
from app.models import CalEvent, Person
from app.store import FirestoreStore


def test_firestore_store_uses_common_collections_and_workspace_scoped_documents():
    client = Mock()
    collection = client.collection.return_value
    collection.where.return_value.stream.return_value = []
    store = FirestoreStore(client, "guest")

    store.people()
    store.save_calendar_token("p_priya", "encrypted")

    assert [call.args[0] for call in client.collection.call_args_list] == ["people", "calendar_connections"]
    query = collection.where.call_args.kwargs["filter"]
    assert query.field_path == "workspaceId"
    assert query.value == "guest"
    client.collection.return_value.document.assert_called_once_with("guest__p_priya")
    client.collection.return_value.document.return_value.set.assert_called_once_with(
        {"encryptedToken": "encrypted", "workspaceId": "guest"})


def test_firestore_store_get_person_uses_scoped_document_id_and_hides_workspace_field():
    client = Mock()
    snapshot = client.collection.return_value.document.return_value.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "id": "p_sam",
        "name": "Sam Wilson",
        "email": "sam@example.com",
        "workspaceId": "company",
    }

    person = FirestoreStore(client, "company").get_person("p_sam")

    client.collection.assert_called_once_with("people")
    client.collection.return_value.document.assert_called_once_with("company__p_sam")
    assert person.id == "p_sam"
    assert person.email == "sam@example.com"


def test_firestore_calendar_uses_common_events_collection_and_scoped_documents():
    client = Mock()
    client.collection.return_value.where.return_value.stream.return_value = []
    calendar = FirestoreCalendar(client, "guest")
    event = CalEvent(id="evt-1", title="Planning", description="", start="2026-10-16T10:00:00Z",
                     end="2026-10-16T11:00:00Z", organizerId="p_sam", attendees=[])

    assert calendar.all_events() == []
    calendar.save_event(event)

    client.collection.assert_called_once_with("events")
    client.collection.return_value.document.assert_called_once_with("guest__evt-1")
    saved = client.collection.return_value.document.return_value.set.call_args.args[0]
    assert saved["workspaceId"] == "guest"
    assert saved["id"] == "evt-1"
    query = client.collection.return_value.where.call_args.kwargs["filter"]
    assert query.field_path == "workspaceId"
    assert query.value == "guest"


def test_guest_person_email_is_updated_without_replacing_other_fields():
    client = Mock()
    reference = client.collection.return_value.document.return_value
    reference.get.return_value.exists = True
    reference.get.return_value.to_dict.return_value = {"email": "real@example.com", "name": "Existing Name"}
    store = FirestoreStore(client, "guest")

    store.ensure_guest_person(Person(id="p_priya", name="Priya Sharma", email="p_priya@example.invalid"))

    client.collection.assert_called_once_with("people")
    client.collection.return_value.document.assert_called_once_with("guest__p_priya")
    reference.update.assert_called_once_with({"email": "p_priya@example.invalid"})


def test_firestore_workspace_id_validation(monkeypatch):
    monkeypatch.setenv("FIRESTORE_WORKSPACE_ID", "guest")
    assert config.firestore_workspace_id() == "guest"

    monkeypatch.setenv("FIRESTORE_WORKSPACE_ID", "../people")
    with pytest.raises(ValueError, match="FIRESTORE_WORKSPACE_ID"):
        config.firestore_workspace_id()
