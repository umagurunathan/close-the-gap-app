"""Settings come from environment variables so the same code runs locally and on Cloud Run."""
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()


def store_kind() -> str:
    return os.getenv("STORE", "memory")


def seed_path() -> str:
    return os.getenv("SEED_PATH", "seed/seed.json")


def cors_origins() -> list[str]:
    return [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]


def now() -> datetime:
    """Current time. NOW env var fixes it (handy for demos and tests)."""
    fixed = os.getenv("NOW")
    if fixed:
        return datetime.fromisoformat(fixed.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


# Tunable numbers (reminders, urgency, reschedule search, metrics assumptions, word lists) live in config/settings.toml.
