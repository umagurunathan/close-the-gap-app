"""Shared Firestore helpers for the persistence adapters."""
from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterable
from typing import Optional, TypeVar

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def encode_model(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


def decode_document(snapshot, model_type: type[T]) -> T | None:
    if not snapshot.exists:
        return None
    return model_type.model_validate(snapshot.to_dict())


def create_if_missing(reference, model: BaseModel) -> bool:
    try:
        reference.create(encode_model(model))
    except AlreadyExists:
        return False
    return True


def new_client(project: str, database: str):
    return firestore.Client(project=project, database=database)


# One request's reads (`[store] request_cache`). A page asks the backend about a dozen questions, and each one used to
# read the same collections from Firestore many times over. While one request runs, each collection and each document
# is read at most once; the request's own writes go to Firestore first and then update what it has read. Nothing is
# kept after the request ends, so a request never sees data older than the moment it started. Background AI threads
# start outside any request, so they always read Firestore directly.
_REQUEST_READS: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("close_the_gap_request_reads",
                                                                                default=None)


def begin_request_reads(enabled: bool) -> None:
    """Called at the start of every request (in its own context, so requests never share what they read)."""
    _REQUEST_READS.set({} if enabled else None)


class RequestReads:
    """What the current request has read from one area. Every method works without a request (it then reads
    Firestore directly), so tests, start-up and background threads behave exactly as before."""

    def __init__(self, workspace_id: str):
        self._workspace_id = workspace_id

    def _entry(self, collection: str) -> Optional[dict]:
        reads = _REQUEST_READS.get()
        if reads is None:
            return None
        return reads.setdefault((self._workspace_id, collection), {"complete": False, "docs": {}})

    def scan(self, collection: str, stream: Callable[[], Iterable]) -> list[dict]:
        """Every document of this area in one collection, in document-id order (as Firestore returns them)."""
        entry = self._entry(collection)
        if entry is not None and entry["complete"]:
            return [data for _, data in sorted(entry["docs"].items()) if data is not None]
        docs = {doc.id: doc.to_dict() for doc in stream()}
        if entry is not None:
            entry["docs"], entry["complete"] = dict(docs), True
        return list(docs.values())

    def get(self, collection: str, document_id: str, fetch: Callable[[], object],
            stream: Callable[[], Iterable]) -> Optional[dict]:
        """One document by its full id, or None when it does not exist. Inside a request the first lookup reads the
        whole collection in one trip: a page looks up many people and meetings one by one, and each collection holds
        only tens of documents per area, so one trip is much faster than one trip per document."""
        entry = self._entry(collection)
        if entry is None:
            snapshot = fetch()
            return snapshot.to_dict() if snapshot.exists else None
        if not entry["complete"] and document_id not in entry["docs"]:
            self.scan(collection, stream)
        return entry["docs"].get(document_id)

    def wrote(self, collection: str, document_id: str, data: Optional[dict]) -> None:
        """After a write has reached Firestore: the new document (None when it was deleted)."""
        entry = self._entry(collection)
        if entry is not None:
            entry["docs"][document_id] = data

    def forget(self, collection: str, document_id: Optional[str] = None) -> None:
        """After a write whose result is not known here: read again from Firestore next time."""
        reads = _REQUEST_READS.get()
        if reads is None:
            return
        if document_id is None:
            reads.pop((self._workspace_id, collection), None)
        elif (entry := reads.get((self._workspace_id, collection))) is not None:
            entry["docs"].pop(document_id, None)
            entry["complete"] = False