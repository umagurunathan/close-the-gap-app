"""Per-user Google Calendar OAuth and Calendar API operations."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from . import config
from .models import CalEvent, EventAttendee, Person
from .store import FirestoreStore, InMemoryStore, Store

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
USERINFO_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class CalendarIntegrationError(RuntimeError):
    """A configuration or Google API error safe to return to the app."""


class GoogleCalendarIntegration:
    def __init__(self, store: Store):
        self.store = store

    def hosted_enabled(self) -> bool:
        return (
            os.getenv("GOOGLE_CALENDAR_ENABLED", "").strip().lower() == "true"
            and config.firebase_auth_enabled()
            and isinstance(self.store, FirestoreStore)
        )

    def configured(self) -> bool:
        local_enabled = (
            os.getenv("GOOGLE_CALENDAR_LOCAL_DEMO_ONLY", "").strip().lower() == "true"
            and config.store_kind().strip().lower() == "memory"
            and isinstance(self.store, InMemoryStore)
        )
        return (local_enabled or self.hosted_enabled()) and all(os.getenv(key) for key in (
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_CALENDAR_REDIRECT_URI",
            "GOOGLE_TOKEN_ENCRYPTION_KEY",
        ))

    def status(self, person_id: str) -> dict:
        configured = self.configured()
        return {"connected": configured and self.store.get_calendar_token(person_id) is not None,
                "configured": configured}

    def authorization_url(self, person_id: str) -> str:
        self._require_config()
        payload = json.dumps(
            {"personId": person_id, "issuedAt": int(time.time()), "nonce": secrets.token_urlsafe(18)},
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(
            os.environ["GOOGLE_OAUTH_CLIENT_SECRET"].encode(), encoded.encode(), hashlib.sha256
        ).digest()
        state = f"{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"
        params = {
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "redirect_uri": os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
            "response_type": "code",
            "scope": f"{CALENDAR_SCOPE} {USERINFO_SCOPE}",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    def finish_authorization(self, code: str, state: str) -> str:
        self._require_config()
        person_id = self._verify_state(state)
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(OAUTH_TOKEN_URL, data={
                    "code": code,
                    "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
                    "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
                    "redirect_uri": os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
                    "grant_type": "authorization_code",
                })
                response.raise_for_status()
                token = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CalendarIntegrationError("Google Calendar authorization could not be completed.") from exc
        if not isinstance(token, dict) or not token.get("access_token"):
            raise CalendarIntegrationError("Google authorization returned an invalid token response.")
        if not token.get("refresh_token"):
            current = self._read_token(person_id)
            if current is None:
                raise CalendarIntegrationError("Google did not return a refresh token. Reconnect and approve access.")
            token["refresh_token"] = current["refresh_token"]
        person = self.store.get_person(person_id)
        if person is None:
            raise CalendarIntegrationError("The selected app user no longer exists.")
        token["google_email"] = self._google_email(token["access_token"])
        if token["google_email"].casefold() != person.email.casefold():
            raise CalendarIntegrationError("Connect using the Google account that matches your directory email.")
        token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
        self._save_token(person_id, token)
        return person_id

    def list_events(self, person_id: str, time_min: datetime, time_max: datetime) -> list[dict]:
        if time_max <= time_min:
            raise ValueError("timeMax must be later than timeMin")
        token = self._access_token(person_id)
        events, page_token = [], None
        while True:
            params = {
                "timeMin": time_min.astimezone(timezone.utc).isoformat(),
                "timeMax": time_max.astimezone(timezone.utc).isoformat(),
                "singleEvents": "true",
                "showDeleted": "true",
                "orderBy": "startTime",
                "maxResults": 2500,
            }
            if page_token:
                params["pageToken"] = page_token
            page = self._get_json(token, f"{CALENDAR_API}/calendars/primary/events", params)
            events.extend(page.get("items", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                return events

    def create_event(self, person_id: str, title: str, description: str, start: datetime, end: datetime,
                     attendees: list[EventAttendee]) -> str:
        guest_list = []
        for attendee in attendees:
            person = self.store.get_person(attendee.personId)
            if person is None:
                raise CalendarIntegrationError("An attendee is no longer in the company directory.")
            guest_list.append({"email": person.email, "optional": attendee.optional})
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "attendees": guest_list,
        }
        result = self._request_json(
            person_id, "POST", f"{CALENDAR_API}/calendars/primary/events?sendUpdates=all", body,
        )
        event_id = result.get("id")
        if not event_id:
            raise CalendarIntegrationError("Google Calendar created an event without returning its identifier.")
        return event_id

    def update_event(self, event: CalEvent) -> None:
        if not event.googleEventId or event.googleCalendarOwnerId != event.organizerId:
            return
        body = {
            "summary": event.title,
            "description": event.description,
            "start": {"dateTime": event.start.isoformat()},
            "end": {"dateTime": event.end.isoformat()},
            "attendees": [
                {"email": person.email, "optional": attendee.optional}
                for attendee in event.attendees
                if (person := self.store.get_person(attendee.personId)) is not None
            ],
        }
        self._request_json(event.googleCalendarOwnerId, "PATCH",
                           f"{CALENDAR_API}/calendars/primary/events/{event.googleEventId}?sendUpdates=all", body)

    def add_attendee(self, event: CalEvent, person_id: str, optional: bool = True) -> None:
        person = self.store.get_person(person_id)
        if person is None:
            raise CalendarIntegrationError("The requested attendee is no longer in the company directory.")
        updated = event.model_copy(deep=True)
        if not any(attendee.personId == person_id for attendee in updated.attendees):
            updated.attendees.append(EventAttendee(personId=person_id, optional=optional))
        self.update_event(updated)

    def delete_event(self, person_id: str, event_id: str) -> None:
        token = self._access_token(person_id)
        try:
            with httpx.Client(timeout=30) as client:
                response = client.delete(
                    f"{CALENDAR_API}/calendars/primary/events/{event_id}?sendUpdates=all",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if response.status_code >= 400:
                    raise CalendarIntegrationError(f"Google Calendar API request failed (HTTP {response.status_code}).")
        except httpx.HTTPError as exc:
            raise CalendarIntegrationError("Could not reach the Google Calendar API.") from exc

    def _request_json(self, person_id: str, method: str, url: str, body: dict) -> dict:
        token = self._access_token(person_id)
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(method, url, json=body,
                                         headers={"Authorization": f"Bearer {token}"})
                if response.status_code >= 400:
                    raise CalendarIntegrationError(
                        f"Google Calendar API request failed (HTTP {response.status_code})."
                    )
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CalendarIntegrationError("Could not complete the Google Calendar API request.") from exc

    def _get_json(self, access_token: str, url: str, params: dict) -> dict:
        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})
                if response.status_code >= 400:
                    raise CalendarIntegrationError(
                        f"Google Calendar API request failed (HTTP {response.status_code})."
                    )
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CalendarIntegrationError("Could not reach the Google Calendar API.") from exc

    def _google_email(self, access_token: str) -> str:
        profile = self._get_json(access_token, "https://www.googleapis.com/oauth2/v2/userinfo", {})
        email = profile.get("email", "")
        if not profile.get("verified_email") or not email:
            raise CalendarIntegrationError("Google did not verify an email address for this account.")
        return email

    def _access_token(self, person_id: str) -> str:
        self._require_config()
        token = self._read_token(person_id)
        if token is None:
            raise CalendarIntegrationError("Connect your Google Calendar before syncing or scheduling.")
        if float(token.get("expires_at", 0)) > time.time() + 60:
            return token["access_token"]
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(OAUTH_TOKEN_URL, data={
                    "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
                    "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
                    "refresh_token": token["refresh_token"],
                    "grant_type": "refresh_token",
                })
                response.raise_for_status()
                refreshed = response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise CalendarIntegrationError("Google Calendar authorization expired. Reconnect your account.") from exc
        token.update(refreshed)
        token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
        self._save_token(person_id, token)
        return token["access_token"]

    def _read_token(self, person_id: str) -> Optional[dict]:
        encrypted = self.store.get_calendar_token(person_id)
        if encrypted is None:
            return None
        try:
            decoded = self._fernet().decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise CalendarIntegrationError(
                "Stored Google Calendar authorization cannot be decrypted. Reconnect the account."
            ) from exc
        return json.loads(decoded)

    def _save_token(self, person_id: str, token: dict) -> None:
        encrypted = self._fernet().encrypt(json.dumps(token).encode()).decode()
        self.store.save_calendar_token(person_id, encrypted)

    def _fernet(self) -> Fernet:
        key = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
        try:
            return Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise CalendarIntegrationError("Set GOOGLE_TOKEN_ENCRYPTION_KEY to a valid Fernet key.") from exc

    def _require_config(self) -> None:
        if not self.configured():
            raise CalendarIntegrationError("Google Calendar is not configured for the active data mode.")
        self._fernet()

    def _verify_state(self, state: str) -> str:
        try:
            encoded, signature = state.split(".", 1)
            expected = hmac.new(os.environ["GOOGLE_OAUTH_CLIENT_SECRET"].encode(),
                                encoded.encode(), hashlib.sha256).digest()
            supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, supplied):
                raise ValueError
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            value = json.loads(payload)
            if int(time.time()) - int(value["issuedAt"]) > 600:
                raise ValueError
            person_id = value["personId"]
            if not self.store.get_person(person_id):
                raise ValueError
            return person_id
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise CalendarIntegrationError("Google authorization state is invalid or expired. Try connecting again.") from exc


# Google Calendar entries that are not meetings: out-of-office, focus-time and working-location blocks, and
# birthdays. They are never imported as meetings. An out-of-office block is not read as an absence either: absences
# come only from "Report an absence" (connecting a leave system or out-of-office is future scope).
NOT_MEETINGS = {"outOfOffice", "focusTime", "workingLocation", "birthday"}


def is_not_a_meeting(event_data: dict) -> bool:
    return event_data.get("eventType", "default") in NOT_MEETINGS


def calendar_event(event_data: dict, owner: Person, people_by_email: dict[str, Person]) -> Optional[CalEvent]:
    """Convert one primary-calendar event to the app's directory-backed event shape."""
    if event_data.get("status") == "cancelled" or not event_data.get("id") or is_not_a_meeting(event_data):
        return None
    organizer_email = event_data.get("organizer", {}).get("email", "").casefold()
    organizer = owner if organizer_email == owner.email.casefold() else people_by_email.get(organizer_email)
    if organizer is None:
        return None
    start = _event_datetime(event_data.get("start", {}))
    end = _event_datetime(event_data.get("end", {}))
    if start is None or end is None or end <= start:
        return None
    attendees = []
    for row in event_data.get("attendees", []):
        person = people_by_email.get(row.get("email", "").casefold())
        if person and person.id != organizer.id:
            attendees.append(EventAttendee(personId=person.id, optional=bool(row.get("optional"))))
    instance_start = event_data.get("originalStartTime") if event_data.get("recurringEventId") else None
    identity = event_data.get("iCalUID")
    if identity:
        identity += ":" + json.dumps(instance_start, sort_keys=True) if instance_start else ""
    else:
        identity = f"{owner.id}:{event_data['id']}"
    local_id = "gcal:" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    return CalEvent(
        id=local_id,
        seriesId=event_data.get("recurringEventId"),
        title=event_data.get("summary") or "Untitled meeting",
        description=event_data.get("description") or "",
        start=start,
        end=end,
        organizerId=organizer.id,
        attendees=attendees,
        googleEventId=event_data["id"],
        googleCalendarOwnerId=owner.id,
    )


def _event_datetime(value: dict) -> Optional[datetime]:
    raw = value.get("dateTime")
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    raw_date = value.get("date")
    if raw_date:
        try:
            return datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
