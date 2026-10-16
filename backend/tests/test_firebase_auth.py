from fastapi.testclient import TestClient

from app import firebase_auth
from app.main import create_app
from app.seed import build_service


def _arjun_email():
    return build_service().store.get_person("p_arjun").email


def _client(monkeypatch, claims):
    monkeypatch.setenv("FIREBASE_AUTH_ENABLED", "true")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "close-the-gap-2026")
    monkeypatch.setattr(firebase_auth, "verify_firebase_token", lambda token, request, audience: claims)
    return TestClient(create_app(build_service()))


def test_firebase_token_maps_verified_email_to_exact_directory_person(monkeypatch):
    client = _client(monkeypatch, {
        "email": _arjun_email(),
        "email_verified": True,
    })

    response = client.get("/me", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 200
    assert response.json()["person"]["id"] == "p_arjun"


def test_firebase_token_cannot_select_another_directory_person(monkeypatch):
    client = _client(monkeypatch, {
        "email": _arjun_email(),
        "email_verified": True,
    })

    response = client.get("/me", headers={
        "Authorization": "Bearer valid-token",
        "X-Person-Id": "p_priya",
    })

    assert response.status_code == 403


def test_firebase_auth_rejects_unmapped_or_unverified_accounts(monkeypatch):
    client = _client(monkeypatch, {
        "email": "someone@example.net",
        "email_verified": True,
    })
    assert client.get("/people", headers={"Authorization": "Bearer valid-token"}).status_code == 403

    client = _client(monkeypatch, {
        "email": _arjun_email(),
        "email_verified": False,
    })
    assert client.get("/people", headers={"Authorization": "Bearer valid-token"}).status_code == 403


def test_firebase_auth_protects_routes_but_keeps_health_public(monkeypatch):
    client = _client(monkeypatch, {
        "email": _arjun_email(),
        "email_verified": True,
    })

    assert client.get("/health").status_code == 200
    assert client.get("/people").status_code == 401


def test_firebase_auth_errors_include_cors_headers(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://close-the-gap-2026.web.app")
    client = _client(monkeypatch, {"email": _arjun_email(), "email_verified": True})

    response = client.get("/data-mode", headers={"Origin": "https://close-the-gap-2026.web.app"})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://close-the-gap-2026.web.app"


def test_firebase_auth_disables_demo_only_endpoints(monkeypatch):
    client = _client(monkeypatch, {
        "email": _arjun_email(),
        "email_verified": True,
    })
    headers = {"Authorization": "Bearer valid-token"}

    assert client.get("/dev/outbox", headers=headers).status_code == 404
    assert client.post("/dev/reset-demo", headers=headers).status_code == 404


def test_global_data_mode_switch_is_limited_to_allowlisted_presenters(monkeypatch):
    from app import data_mode

    arjun_email = _arjun_email()
    claims = {"email": arjun_email, "email_verified": True}
    monkeypatch.setenv("DATA_MODE_SWITCH_ENABLED", "true")
    monkeypatch.setenv("DATA_MODE_ADMIN_EMAILS", arjun_email)

    class FakeRegistry:
        def __init__(self):
            self.mode = "memory"

        def get(self):
            return self.mode

        def set(self, mode):
            self.mode = mode

    registry = FakeRegistry()
    monkeypatch.setattr(data_mode, "FirestoreDataMode", lambda: registry)
    client = _client(monkeypatch, claims)
    headers = {"Authorization": "Bearer unit-test-token"}

    response = client.get("/data-mode", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "mode": "memory", "canSwitch": True}

    claims["email"] = "sam@example.com"
    response = client.post("/data-mode", headers=headers, json={"mode": "firestore"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Only an authorized demo presenter can change the app-wide data mode."

    from app import main
    from app.calendar import SimCalendar
    from app.service import Service
    from app.store import FirestoreStore

    claims["email"] = arjun_email
    next_service = Service(FirestoreStore(object()), SimCalendar([]))
    monkeypatch.setattr(main, "build_service", lambda mode: next_service)
    response = client.post("/data-mode", headers=headers, json={"mode": "firestore"})
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "mode": "firestore", "canSwitch": True}
    assert registry.mode == "firestore"
