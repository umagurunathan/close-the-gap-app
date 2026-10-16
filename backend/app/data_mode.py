"""Shared selection for the hosted seed and Firestore demo modes."""
from __future__ import annotations

from . import config
from .firestore import new_client

VALID_MODES = {"memory", "firestore"}


class FirestoreDataMode:
    def __init__(self):
        client = new_client(config.firestore_project(), config.firestore_database())
        workspace_id = config.firestore_workspace_id()
        self._document = client.collection("metadata").document(f"{workspace_id}__demo_mode")

    def get(self) -> str:
        snapshot = self._document.get()
        if not snapshot.exists:
            mode = config.store_kind().strip().lower()
            self.set(mode)
            return mode
        mode = (snapshot.to_dict() or {}).get("mode")
        if mode not in VALID_MODES:
            raise RuntimeError("Firestore workspace metadata has an unsupported data mode.")
        return mode

    def set(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Unsupported data mode {mode!r}; expected 'memory' or 'firestore'.")
        self._document.set({"mode": mode, "workspaceId": config.firestore_workspace_id()})
