"""Settings come from environment variables so the same code runs locally and on Cloud Run."""
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()


def store_kind() -> str:
    return os.getenv("STORE", "memory")


def llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "rules").strip().lower()


def google_cloud_project() -> str:
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if not project:
        raise RuntimeError("Set GOOGLE_CLOUD_PROJECT when using a Google Cloud service")
    return project


def firestore_project() -> str:
    return os.getenv("FIRESTORE_PROJECT_ID") or google_cloud_project()


def firestore_database() -> str:
    return os.getenv("FIRESTORE_DATABASE", "(default)")


def firestore_workspace_id() -> str:
    workspace_id = os.getenv("FIRESTORE_WORKSPACE_ID", "company").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", workspace_id):
        raise ValueError(
            "FIRESTORE_WORKSPACE_ID must start with a lowercase letter and contain only lowercase letters, "
            "digits, or underscores."
        )
    return workspace_id


def firebase_auth_enabled() -> bool:
    return os.getenv("FIREBASE_AUTH_ENABLED", "").strip().lower() == "true"


def data_mode_switch_enabled() -> bool:
    return os.getenv("DATA_MODE_SWITCH_ENABLED", "").strip().lower() == "true"


def data_mode_admin_emails() -> set[str]:
    return {
        email.strip().casefold()
        for email in os.getenv("DATA_MODE_ADMIN_EMAILS", "").split(",")
        if email.strip()
    }


def vertex_ai_location() -> str:
    return os.getenv("VERTEX_AI_LOCATION", "asia-southeast1")


def gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def seed_path() -> str:
    return os.getenv("SEED_PATH", "seed/seed.json")


def cors_origins() -> list[str]:
    return [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]


def web_app_url() -> str:
    return os.getenv("WEB_APP_URL", "http://localhost:5173").rstrip("/")


def now() -> datetime:
    """Current time. NOW env var fixes it (handy for demos and tests)."""
    fixed = os.getenv("NOW")
    if fixed:
        return datetime.fromisoformat(fixed.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


# Tunable numbers (reminders, urgency, reschedule search, metrics assumptions, word lists) live in config/settings.toml.
