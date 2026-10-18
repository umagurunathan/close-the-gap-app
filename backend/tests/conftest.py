"""Runs before every test file: tests always use the in-memory store, even when the local .env points at Firestore
(load_dotenv never overrides a variable that is already set), so a test can never write to the real database."""
import os
from datetime import datetime, timezone

import pytest

os.environ["STORE"] = "memory"
os.environ["AI_ENABLED"] = "false"   # the product runs Gemini; the tests use the rules (or fakes) and need no network
for name in ("FIRESTORE_PROJECT_ID", "FIRESTORE_DATABASE"):
    os.environ.pop(name, None)

from app import config  # noqa: E402  (after the environment is set)

REAL_NOW = config.now                                    # the product's clock, for the test that checks it is real
FIXED_NOW = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)   # Sun 8 Nov 2026, 9:00 UTC


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    """The product always runs on the real clock. Only the tests fix it, so they always see the same data."""
    monkeypatch.setattr(config, "now", lambda: FIXED_NOW)
