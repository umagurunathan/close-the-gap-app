"""Runs before every test file: tests always use the in-memory store, even when the local .env points at Firestore
(load_dotenv never overrides a variable that is already set), so a test can never write to the real database."""
import os

os.environ["STORE"] = "memory"
os.environ["AI_ENABLED"] = "false"   # the product runs Gemini; the tests use the rules (or fakes) and need no network
os.environ["NOW"] = "2026-11-08T09:00:00Z"
for name in ("FIRESTORE_PROJECT_ID", "FIRESTORE_DATABASE"):
    os.environ.pop(name, None)
