"""Google Meet OAuth and transcript import."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from . import config
from .models import CalEvent, Note
from .store import Store

MEET_SCOPE = "https://www.googleapis.com/auth/meetings.space.readonly"
USERINFO_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
MEET_API = "https://meet.googleapis.com/v2"
MEET_URL_RE = re.compile(r"^[a-z0-9-]{3,128}$", re.IGNORECASE)
TRANSCRIPT_NOTE_PREFIX = "meet-transcript-"


class MeetIntegrationError(RuntimeError):
    """A configuration or Google API error safe to return to the app."""


class GoogleMeetIntegration:
    def __init__(self, store: Store, calendar):
        self.store = store
        self.calendar = calendar

    @staticmethod
    def configured() -> bool:
        return all(os.getenv(key) for key in (
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI",
            "GOOGLE_TOKEN_ENCRYPTION_KEY",
        ))

    def status(self, person_id: str) -> dict:
        return {"connected": self.store.get_meet_token(person_id) is not None, "configured": self.configured()}

    def authorization_url(self, person_id: str) -> str:
        self._require_config()
        payload = json.dumps(
            {"personId": person_id, "issuedAt": int(time.time()), "nonce": secrets.token_urlsafe(18)},
            separators=(",", ":"),
        ).encode()
        state = self._sign_state(payload)
        params = {
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "redirect_uri": os.environ["GOOGLE_OAUTH_REDIRECT_URI"],
            "response_type": "code",
            "scope": f"{MEET_SCOPE} {USERINFO_SCOPE}",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
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
                    "redirect_uri": os.environ["GOOGLE_OAUTH_REDIRECT_URI"],
                    "grant_type": "authorization_code",
                })
                response.raise_for_status()
                token = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MeetIntegrationError("Google authorization could not be completed.") from exc
        if not isinstance(token, dict) or not token.get("access_token"):
            raise MeetIntegrationError("Google authorization returned an invalid token response.")
        if not token.get("refresh_token"):
            current = self._read_token(person_id)
            if current is None:
                raise MeetIntegrationError("Google did not return a refresh token. Reconnect and approve access.")
            token["refresh_token"] = current["refresh_token"]
        person = self.store.get_person(person_id)
        if person is None:
            raise MeetIntegrationError("The selected app user no longer exists.")
        token["google_email"] = self._google_email(token["access_token"])
        if token["google_email"].casefold() != person.email.casefold():
            raise MeetIntegrationError("Connect using the Google account that matches the meeting organizer's email.")
        token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
        self._save_token(person_id, token)
        return person_id

    def link_meeting(self, item_id: str, caller: str, meet_url: str) -> str:
        _, event = self._item_event(item_id)
        if caller != event.organizerId:
            raise PermissionError("only the meeting organizer can link a Google Meet")
        parsed = urlsplit(meet_url.strip())
        code = parsed.path.strip("/")
        if parsed.scheme != "https" or parsed.netloc.lower() != "meet.google.com" or not MEET_URL_RE.fullmatch(code):
            raise ValueError("enter a Google Meet link such as https://meet.google.com/abc-defg-hij")
        event.meetUrl = f"https://meet.google.com/{code}"
        self.calendar.save_event(event)
        return event.meetUrl

    def meeting_status(self, item_id: str, caller: str) -> dict:
        item, event = self._item_event(item_id)
        if caller not in self._invitees(event):
            raise PermissionError("only meeting invitees can view this meeting")
        return {
            "meetUrl": event.meetUrl,
            "configured": self.configured(),
            "connected": self.store.get_meet_token(event.organizerId) is not None,
        }

    def import_transcript(self, item_id: str, caller: str, shared_with: list[str]) -> Note:
        _, event = self._item_event(item_id)
        if caller != event.organizerId:
            raise PermissionError("only the meeting organizer can import a Google Meet transcript")
        if not event.meetUrl:
            raise ValueError("link a Google Meet to this meeting first")
        readers = list(dict.fromkeys(shared_with))
        if not set(readers) <= self._invitees(event):
            raise ValueError("transcripts can only be shared with meeting invitees")
        token = self._access_token(event.organizerId)
        transcript_id, transcript_text = self._fetch_transcript(token, event)
        doc_id = TRANSCRIPT_NOTE_PREFIX + hashlib.sha256(transcript_id.encode()).hexdigest()[:24]
        note = Note(
            docId=doc_id,
            modifiedAt=config.now(),
            text=transcript_text,
            sharedWith=readers,
            source="google_meet_transcript",
            sourceId=transcript_id,
        )
        existing = next((index for index, current in enumerate(event.notes) if current.docId == doc_id), None)
        if existing is None:
            event.notes.append(note)
        else:
            event.notes[existing] = note
        self.calendar.save_event(event)
        return note

    def _fetch_transcript(self, access_token: str, event: CalEvent) -> tuple[str, str]:
        code = urlsplit(event.meetUrl or "").path.strip("/")
        records, page_token = [], None
        while True:
            params = {"filter": f"space.meeting_code = '{code}'", "pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            page = self._get_json(access_token, f"{MEET_API}/conferenceRecords", params)
            records.extend(page.get("conferenceRecords", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        nearby = []
        for record in records:
            start_text = record.get("startTime")
            if not start_text:
                continue
            start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
            if event.start - timedelta(hours=2) <= start <= event.end + timedelta(hours=2):
                nearby.append((abs((start - event.start).total_seconds()), record))
        if not nearby:
            raise MeetIntegrationError("No finished Google Meet session matched this event and meeting code.")
        record = min(nearby, key=lambda row: row[0])[1]
        record_name = record.get("name")
        if not record_name:
            raise MeetIntegrationError("Google Meet returned a conference record without an identifier.")
        transcripts = self._get_json(access_token, f"{MEET_API}/{record_name}/transcripts", {
            "pageSize": 100,
        }).get("transcripts", [])
        generated = [transcript for transcript in transcripts if transcript.get("state") == "FILE_GENERATED"]
        if not generated:
            raise MeetIntegrationError("No generated transcript is available yet. Confirm transcription was enabled and try again later.")
        transcript = max(generated, key=lambda row: row.get("startTime", ""))
        transcript_name = transcript.get("name")
        if not transcript_name:
            raise MeetIntegrationError("Google Meet returned a transcript without an identifier.")
        entries, page_token = [], None
        while True:
            params = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            page = self._get_json(access_token, f"{MEET_API}/{transcript_name}/entries", params)
            entries.extend(page.get("transcriptEntries", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        entries.sort(key=lambda entry: entry.get("startTime", ""))
        text = "\n".join(entry["text"].strip() for entry in entries if entry.get("text", "").strip())
        if not text:
            raise MeetIntegrationError("The generated transcript contains no readable transcript entries.")
        return transcript_name, text

    def _get_json(self, access_token: str, path: str, params: dict) -> dict:
        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(path, params=params, headers={"Authorization": f"Bearer {access_token}"})
                if response.status_code >= 400:
                    raise MeetIntegrationError(f"Google Meet API request failed (HTTP {response.status_code}).")
                return response.json()
        except httpx.HTTPError as exc:
            raise MeetIntegrationError("Could not reach the Google Meet API.") from exc

    def _google_email(self, access_token: str) -> str:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code >= 400:
                    raise MeetIntegrationError(f"Google account verification failed (HTTP {response.status_code}).")
                profile = response.json()
        except httpx.HTTPError as exc:
            raise MeetIntegrationError("Could not verify the connected Google account.") from exc
        email = profile.get("email", "")
        if not profile.get("verified_email") or not email:
            raise MeetIntegrationError("Google did not verify an email address for the connected account.")
        return email

    def _access_token(self, person_id: str) -> str:
        token = self._read_token(person_id)
        if token is None:
            raise MeetIntegrationError("The organizer must connect Google Meet before importing a transcript.")
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
            raise MeetIntegrationError("Google Meet authorization expired. Reconnect the organizer account.") from exc
        token.update(refreshed)
        token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
        self._save_token(person_id, token)
        return token["access_token"]

    def _read_token(self, person_id: str) -> Optional[dict]:
        encrypted = self.store.get_meet_token(person_id)
        if encrypted is None:
            return None
        try:
            decoded = self._fernet().decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise MeetIntegrationError("Stored Google Meet authorization cannot be decrypted. Reconnect the account.") from exc
        return json.loads(decoded)

    def _save_token(self, person_id: str, token: dict) -> None:
        encrypted = self._fernet().encrypt(json.dumps(token).encode()).decode()
        self.store.save_meet_token(person_id, encrypted)

    def _fernet(self) -> Fernet:
        key = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
        try:
            return Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise MeetIntegrationError("Set GOOGLE_TOKEN_ENCRYPTION_KEY to a valid Fernet key.") from exc

    def _require_config(self) -> None:
        if not self.configured():
            raise MeetIntegrationError(
                "Google Meet integration is not configured. Set the OAuth client, redirect URI, and token encryption key."
            )
        self._fernet()

    def _sign_state(self, payload: bytes) -> str:
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(os.environ["GOOGLE_OAUTH_CLIENT_SECRET"].encode(), encoded.encode(), hashlib.sha256).digest()
        return f"{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"

    def _verify_state(self, state: str) -> str:
        try:
            encoded, signature = state.split(".", 1)
            expected = hmac.new(os.environ["GOOGLE_OAUTH_CLIENT_SECRET"].encode(), encoded.encode(), hashlib.sha256).digest()
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
            raise MeetIntegrationError("Google authorization state is invalid or expired. Try connecting again.") from exc

    def _item_event(self, item_id: str):
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("item not found")
        event = self.calendar.get(item.event.calendarEventId)
        if event is None:
            raise LookupError("meeting not found")
        return item, event

    @staticmethod
    def _invitees(event: CalEvent) -> set[str]:
        return {event.organizerId, *(attendee.personId for attendee in event.attendees)}
