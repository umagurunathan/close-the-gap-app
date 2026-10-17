"""Firebase ID-token verification and mapping to one directory person. A request without a token is a guest in
the demo area; a request with a valid token is that person in the company area."""
from __future__ import annotations

import logging
import os
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import verify_firebase_token

from .store import Store

log = logging.getLogger("close_the_gap.firebase_auth")

PUBLIC_PATHS = {
    "/",
    "/health",
    "/integrations/google-calendar/callback",
    "/integrations/google-meet/callback",
    # Cloud Scheduler sends a Google-signed OIDC token here, not a Firebase ID token. The endpoint checks it itself
    # (main.py require_scheduler), so this middleware must not try to read it as a Firebase sign-in.
    "/jobs/run-reminders",
}


def install_firebase_auth(app: FastAPI, store: Store | Callable[[], Store]) -> None:
    if os.getenv("FIREBASE_AUTH_ENABLED", "").strip().lower() != "true":
        return

    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise RuntimeError("Set FIREBASE_PROJECT_ID when FIREBASE_AUTH_ENABLED=true.")

    google_request = GoogleAuthRequest()

    @app.middleware("http")
    async def verify_firebase_identity(request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        if not authorization:
            # no sign-in: a guest, who works in the demo area as one of the demo people
            return await call_next(request)
        scheme, _, token = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            return JSONResponse({"detail": "Your sign-in could not be read. Please sign in again."}, status_code=401)

        try:
            claims = verify_firebase_token(token, google_request, audience=project_id)
        except (GoogleAuthError, ValueError) as exc:
            log.warning("Firebase ID token could not be verified: %s", exc)
            return JSONResponse({"detail": "Your sign-in expired. Please sign in again."}, status_code=401)

        email = claims.get("email")
        if not isinstance(email, str) or not email or claims.get("email_verified") is not True:
            return JSONResponse({"detail": "Use a Google account with a verified email address."}, status_code=403)

        current_store = store() if callable(store) else store
        matches = [
            person for person in current_store.people()
            if not person.isGroup and person.email.casefold() == email.casefold()
        ]
        if len(matches) != 1:
            return JSONResponse(
                {"detail": "This Google account isn't in the company directory. You can keep using the demo.",
                 "code": "not_in_directory"},
                status_code=403,
            )

        person_id = matches[0].id
        requested_person = request.headers.get("x-person-id")
        if requested_person and requested_person != person_id:
            return JSONResponse({"detail": "You can only act as the person linked to your Google account."},
                                status_code=403)

        request.state.person_id = person_id
        request.state.email = email
        return await call_next(request)
