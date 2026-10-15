from unittest.mock import Mock

import pytest

from app import config
from app.calendar import FirestoreCalendar
from app.models import Person
from app.store import FirestoreStore


def test_firestore_store_prefix_is_applied_to_all_collection_access():
    client = Mock()
    client.collection.return_value.stream.return_value = []
    store = FirestoreStore(client, "public_demo_")

    store.people()
    store.save_calendar_token("p_priya", "encrypted")
    store._collection("metadata")

    assert [call.args[0] for call in client.collection.call_args_list] == [
        "public_demo_people",
        "public_demo_calendar_connections",
        "public_demo_metadata",
    ]


def test_firestore_calendar_prefix_is_applied_to_events():
    client = Mock()

    FirestoreCalendar(client, "public_demo_")

    client.collection.assert_called_once_with("public_demo_events")


def test_public_demo_person_email_is_updated_without_replacing_other_fields():
    client = Mock()
    reference = client.collection.return_value.document.return_value
    reference.get.return_value.exists = True
    reference.get.return_value.to_dict.return_value = {"email": "real@example.com", "name": "Existing Name"}
    store = FirestoreStore(client, "public_demo_")

    store.ensure_public_demo_person(Person(id="p_priya", name="Priya Sharma", email="p_priya@example.invalid"))

    reference.update.assert_called_once_with({"email": "p_priya@example.invalid"})


def test_firestore_collection_prefix_validation(monkeypatch):
    monkeypatch.setenv("FIRESTORE_COLLECTION_PREFIX", "public_demo_")
    assert config.firestore_collection_prefix() == "public_demo_"

    monkeypatch.setenv("FIRESTORE_COLLECTION_PREFIX", "../people")
    with pytest.raises(ValueError, match="FIRESTORE_COLLECTION_PREFIX"):
        config.firestore_collection_prefix()
