import pytest

from app import data_mode


class FakeDocument:
    def __init__(self):
        self.value = None

    def get(self):
        return type("Snapshot", (), {
            "exists": self.value is not None,
            "to_dict": lambda _self: self.value,
        })()

    def set(self, value):
        self.value = value


class FakeClient:
    def __init__(self):
        self.doc = FakeDocument()

    def collection(self, name):
        assert name == "metadata"
        return self

    def document(self, name):
        assert name == "company__demo_mode"
        return self.doc


def test_firestore_data_mode_defaults_from_store_and_persists(monkeypatch):
    client = FakeClient()
    monkeypatch.setenv("STORE", "firestore")
    monkeypatch.setenv("FIRESTORE_PROJECT_ID", "test-project")
    monkeypatch.setenv("FIRESTORE_WORKSPACE_ID", "company")
    monkeypatch.setattr(data_mode, "new_client", lambda project, database: client)
    registry = data_mode.FirestoreDataMode()

    assert registry.get() == "firestore"
    assert client.doc.value == {"mode": "firestore", "workspaceId": "company"}
    registry.set("memory")
    assert registry.get() == "memory"


def test_firestore_data_mode_rejects_invalid_saved_value(monkeypatch):
    client = FakeClient()
    client.doc.value = {"mode": "unsupported"}
    monkeypatch.setenv("FIRESTORE_PROJECT_ID", "test-project")
    monkeypatch.setenv("FIRESTORE_WORKSPACE_ID", "company")
    monkeypatch.setattr(data_mode, "new_client", lambda project, database: client)

    with pytest.raises(RuntimeError, match="unsupported data mode"):
        data_mode.FirestoreDataMode().get()
