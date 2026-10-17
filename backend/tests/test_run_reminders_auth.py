from fastapi.testclient import TestClient
from google.oauth2 import id_token

from app import firebase_auth
from app.main import create_app
from app.seed import build_service

AUDIENCE = "https://close-the-gap-api.example.run.app/jobs/run-reminders"
SCHEDULER = "reminder-scheduler@close-the-gap-2026.iam.gserviceaccount.com"


def _client(monkeypatch, claims=None, error=None):
    """The app with the reminder job configured. The Google token check is replaced by a fake that returns
    `claims`, or raises `error`, and records what it was asked to verify."""
    monkeypatch.setenv("RUN_REMINDERS_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("REMINDERS_SCHEDULER_SA", SCHEDULER)
    seen = []

    def fake_verify(token, request, audience=None):
        seen.append({"token": token, "audience": audience})
        if error:
            raise error
        return claims

    monkeypatch.setattr(id_token, "verify_oauth2_token", fake_verify)
    return TestClient(create_app(build_service())), seen


def _scheduler_claims(**overrides):
    return {"email": SCHEDULER, "email_verified": True, **overrides}


def test_missing_token_is_refused(monkeypatch):
    client, seen = _client(monkeypatch, claims=_scheduler_claims())

    assert client.post("/jobs/run-reminders").status_code == 401
    assert seen == []


def test_token_that_is_not_bearer_is_refused(monkeypatch):
    client, seen = _client(monkeypatch, claims=_scheduler_claims())

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Basic nope"}).status_code == 401
    assert seen == []


def test_token_that_fails_google_verification_is_refused(monkeypatch):
    # wrong audience, expired, or not signed by Google all surface as ValueError from the verifier
    client, _ = _client(monkeypatch, error=ValueError("Token has wrong audience"))

    response = client.post("/jobs/run-reminders", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401


def test_google_unreachable_is_refused_not_a_server_error(monkeypatch):
    # the verifier fetches Google's keys; if that fails, the call is refused (401), not a 500
    from google.auth.exceptions import TransportError
    client, _ = _client(monkeypatch, error=TransportError("could not fetch certificates"))

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"}).status_code == 401


def test_reminders_run_for_the_company_area_only(monkeypatch):
    """The demo runs on a fixed clock, so reminders there would only pile up demo emails while people look."""
    import app.main as main
    demo, company = build_service(), build_service()
    calls = []
    monkeypatch.setattr(demo, "run_reminders", lambda: calls.append("demo") or 0)
    monkeypatch.setattr(company, "run_reminders", lambda: calls.append("company") or 2)
    monkeypatch.setattr(main, "build_service", lambda: demo)
    monkeypatch.setattr(main, "build_company_service", lambda: company)
    monkeypatch.setenv("RUN_REMINDERS_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("REMINDERS_SCHEDULER_SA", SCHEDULER)
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda token, request, audience=None: _scheduler_claims())
    client = TestClient(main.create_app())

    response = client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"})

    assert response.json() == {"reminders_sent": 2} and calls == ["company"]


def test_token_for_another_service_account_is_refused(monkeypatch):
    client, _ = _client(monkeypatch, claims=_scheduler_claims(email="someone-else@close-the-gap-2026.iam.gserviceaccount.com"))

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"}).status_code == 403


def test_a_person_token_is_refused(monkeypatch):
    """Your own Google user (not the scheduler account) must not be able to run the job."""
    client, _ = _client(monkeypatch, claims=_scheduler_claims(email="someone@example.com"))

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"}).status_code == 403


def test_unverified_email_is_refused(monkeypatch):
    client, _ = _client(monkeypatch, claims=_scheduler_claims(email_verified=False))

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"}).status_code == 403


def test_scheduler_token_runs_the_job_for_its_audience(monkeypatch):
    client, seen = _client(monkeypatch, claims=_scheduler_claims())

    response = client.post("/jobs/run-reminders", headers={"Authorization": "Bearer scheduler-token"})

    assert response.status_code == 200
    assert isinstance(response.json()["reminders_sent"], int)
    assert seen == [{"token": "scheduler-token", "audience": AUDIENCE}]


def test_scheduler_email_match_ignores_case(monkeypatch):
    client, _ = _client(monkeypatch, claims=_scheduler_claims(email=SCHEDULER.upper()))

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"}).status_code == 200


def test_unconfigured_job_refuses_every_call(monkeypatch):
    """Fail closed: with no audience or scheduler account set, even a valid-looking token is refused."""
    client, seen = _client(monkeypatch, claims=_scheduler_claims())
    monkeypatch.delenv("RUN_REMINDERS_AUDIENCE")

    assert client.post("/jobs/run-reminders", headers={"Authorization": "Bearer t"}).status_code == 403
    assert seen == []


def test_scheduler_token_passes_the_firebase_middleware(monkeypatch):
    """With Firebase sign-in on, the middleware must not read the scheduler's Bearer token as a Firebase token."""
    monkeypatch.setenv("FIREBASE_AUTH_ENABLED", "true")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "close-the-gap-2026")
    firebase_calls = []
    monkeypatch.setattr(firebase_auth, "verify_firebase_token",
                        lambda token, request, audience: firebase_calls.append(token) or {})
    client, seen = _client(monkeypatch, claims=_scheduler_claims())

    response = client.post("/jobs/run-reminders", headers={"Authorization": "Bearer scheduler-token"})

    assert response.status_code == 200
    assert firebase_calls == []
    assert len(seen) == 1
