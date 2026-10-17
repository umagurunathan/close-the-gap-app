"""Settings come from environment variables so the same code runs locally and on Cloud Run."""
import json
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()


def store_kind() -> str:
    """Where the data lives. Locally, memory unless set (tests and quick runs). On Cloud Run (K_SERVICE is set there)
    it must be Firestore: the backend refuses to start otherwise, so a lost setting fails the new revision (Cloud Run
    keeps serving the last good one) instead of quietly serving data that is never saved."""
    kind = os.getenv("STORE", "memory").strip().lower()
    if os.getenv("K_SERVICE") and kind != "firestore":
        raise RuntimeError(f"STORE must be 'firestore' on Cloud Run (got {kind!r}). Set it with --update-env-vars.")
    return kind


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


def _area_name(variable: str, default: str) -> str:
    name = os.getenv(variable, default).strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"{variable} must start with a lowercase letter and contain only lowercase letters, "
                         "digits, or underscores.")
    return name


def firestore_workspace_id() -> str:
    """The company area: people who sign in with Google, and only their own data."""
    return _area_name("FIRESTORE_WORKSPACE_ID", "company")


def demo_workspace_id() -> str:
    """The demo area: everyone who has not signed in, acting as one of the demo people (seed.json)."""
    return _area_name("FIRESTORE_DEMO_WORKSPACE_ID", "guest")


def company_directory() -> list[dict]:
    """The real people who may sign in: a JSON list of {id, name, email, title, department, managerId}. Private:
    Secret Manager on Cloud Run, the git-ignored .env locally; never in the code."""
    raw = os.getenv("COMPANY_DIRECTORY", "").strip()
    if not raw:
        return []
    people = json.loads(raw)
    if not isinstance(people, list) or not all(isinstance(p, dict) and p.get("id") and p.get("email") for p in people):
        raise ValueError("COMPANY_DIRECTORY must be a JSON list of people, each with at least an id and an email.")
    return people


def firebase_auth_enabled() -> bool:
    return os.getenv("FIREBASE_AUTH_ENABLED", "").strip().lower() == "true"


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


def run_reminders_audience() -> str:
    """The exact URL Cloud Scheduler's OIDC token is issued for, e.g. https://<service>/jobs/run-reminders.
    Empty means the job is not configured, and it refuses every call (fail closed)."""
    return os.getenv("RUN_REMINDERS_AUDIENCE", "").strip()


def scheduler_service_account() -> str:
    """The only service account allowed to call /jobs/run-reminders. Empty means the job refuses every call."""
    return os.getenv("REMINDERS_SCHEDULER_SA", "").strip().lower()


def now() -> datetime:
    """Current time for the demo area. NOW env var fixes it (handy for demos and tests); the company area always
    uses the real clock (real_now), because real people's meetings come from their real calendars."""
    fixed = os.getenv("NOW")
    if fixed:
        return datetime.fromisoformat(fixed.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def real_now() -> datetime:
    return datetime.now(timezone.utc)


# Tunable numbers (reminders, urgency, reschedule search, metrics assumptions, word lists) live in config/settings.toml.
