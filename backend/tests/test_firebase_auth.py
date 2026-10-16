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


def test_without_sign_in_a_visitor_is_a_guest_in_the_demo(monkeypatch):
    client = _client(monkeypatch, {"email": _arjun_email(), "email_verified": True})

    assert client.get("/health").status_code == 200
    # no token: a guest, who may act as a demo person but must choose one
    assert client.get("/me", headers={"X-Person-Id": "p_priya"}).status_code == 200
    assert client.get("/me").status_code == 401
    assert client.get("/session").json() == {"signedIn": False, "personId": None, "area": "demo"}
    # a token that cannot be read is still refused
    assert client.get("/me", headers={"Authorization": "Basic nope"}).status_code == 401


def test_firebase_auth_errors_include_cors_headers(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://close-the-gap-2026.web.app")
    client = _client(monkeypatch, {"email": "someone@example.net", "email_verified": True})

    response = client.get("/me", headers={"Origin": "https://close-the-gap-2026.web.app",
                                          "Authorization": "Bearer valid-token"})

    assert response.status_code == 403
    assert response.json()["code"] == "not_in_directory"
    assert response.headers["access-control-allow-origin"] == "https://close-the-gap-2026.web.app"


def test_signed_in_people_cannot_reset_the_demo_and_see_only_their_own_emails(monkeypatch):
    client = _client(monkeypatch, {"email": _arjun_email(), "email_verified": True})
    headers = {"Authorization": "Bearer valid-token"}

    assert client.post("/dev/reset-demo", headers=headers).status_code == 403
    assert all(m["to"] == _arjun_email() for m in client.get("/dev/outbox", headers=headers).json())
    assert client.post("/dev/reset-demo").status_code == 200   # a guest may reset the demo


def test_the_two_areas_never_mix(monkeypatch):
    """The demo and the company are separate areas; neither side can reach the other."""
    import json
    monkeypatch.setenv("FIREBASE_AUTH_ENABLED", "true")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "close-the-gap-2026")
    monkeypatch.setenv("COMPANY_DIRECTORY", json.dumps([
        {"id": "p_real", "name": "Real Person", "email": "real.person@example.org", "title": "Software Engineer"}]))
    claims = {"email": "real.person@example.org", "email_verified": True}
    monkeypatch.setattr(firebase_auth, "verify_firebase_token", lambda token, request, audience: claims)
    client = TestClient(create_app())
    signed = {"Authorization": "Bearer valid-token"}

    # the real person sees only the company: themselves, no demo people, no demo meetings
    assert client.get("/me", headers=signed).json()["person"]["id"] == "p_real"
    assert [p["id"] for p in client.get("/people", headers=signed).json()] == ["p_real"]
    assert client.get("/items", params={"mode": "attendee"}, headers=signed).json()["needsAction"] == []
    assert client.get("/session", headers=signed).json()["area"] == "company"
    # a guest cannot act as the real person, and sees only the demo people
    assert client.get("/me", headers={"X-Person-Id": "p_real"}).status_code == 401
    guest_people = [p["id"] for p in client.get("/people").json()]
    assert "p_real" not in guest_people and "p_priya" in guest_people
    # a demo person's email is not in the company directory, so it cannot sign in
    claims["email"] = _arjun_email()
    assert client.get("/me", headers=signed).status_code == 403
