"""Shared Firestore helpers for the persistence adapters."""
from __future__ import annotations

from typing import TypeVar

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