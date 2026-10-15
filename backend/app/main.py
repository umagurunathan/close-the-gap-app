"""The API. Every endpoint is listed, with its shapes, at /docs when the server runs. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

import ipaddress
from datetime import date, timedelta
from typing import Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import config, notify
from .google_meet import GoogleMeetIntegration, MeetIntegrationError
from .google_calendar import CalendarIntegrationError, GoogleCalendarIntegration
from .firebase_auth import install_firebase_auth
from .models import (
    Absence, AbsenceCreate, AbsenceSource, ActionRequest, AttendeeAdd, AttendeeItems, DataModeRequest, DirectoryEntry, EventCreate, HistoryEvent,
    MeetingActionRequest, OrganizerMeeting,
    LeaveSystemRequest, ScheduleResult,
    MeetingItem, MeetLinkUpdate, MeetStatus, MeResponse, Metrics, Note, NoteCreate, NoteDraft, NoteDraftAvailable,
    ProposedTime, ProxyCandidate, TranscriptImportRequest,
    ProxyRequest, ProxyRequestView, RespondRequest,
)
from .seed import build_service
from .service import Service
from .settings import settings as S
from .store import FirestoreStore


def create_app(service: Optional[Service] = None) -> FastAPI:
    mode_registry = None
    if config.data_mode_switch_enabled():
        if not config.firebase_auth_enabled():
            raise RuntimeError("DATA_MODE_SWITCH_ENABLED requires FIREBASE_AUTH_ENABLED=true.")
        if not config.data_mode_admin_emails():
            raise RuntimeError("Set DATA_MODE_ADMIN_EMAILS when DATA_MODE_SWITCH_ENABLED=true.")
        from .data_mode import FirestoreDataMode
        mode_registry = FirestoreDataMode()
        initial_mode = mode_registry.get()
    else:
        initial_mode = None
    svc = service or build_service(mode=initial_mode)
    if service is None and S.ai.enabled and S.ai.warm_up_on_start:
        import threading
        from agents.recommender_ai import warm_up
        threading.Thread(target=warm_up, name="ai-warm-up", daemon=True).start()   # never delays the start
    meet = GoogleMeetIntegration(svc.store, svc.calendar)
    calendar = GoogleCalendarIntegration(svc.store)
    svc.google_calendar = calendar
    app = FastAPI(title="Close the Gap API", version="0.2")
    install_firebase_auth(app, lambda: svc.store)
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_methods=["*"], allow_headers=["*"])

    def me(request: Request, x_person_id: Optional[str] = Header(default=None)) -> str:
        """Resolve the verified Firebase identity, or the local demo persona when auth is disabled."""
        if config.firebase_auth_enabled():
            person_id = getattr(request.state, "person_id", None)
            if not person_id:
                raise HTTPException(401, "Sign in with Google to continue.")
            if x_person_id and x_person_id != person_id:
                raise HTTPException(403, "You can only act as the person linked to your Google account.")
            return person_id
        if not x_person_id or not svc.store.get_person(x_person_id):
            raise HTTPException(401, "Please choose who you are signed in as.")
        return x_person_id

    def guard(fn):
        try:
            return fn()
        except LookupError as e:
            raise HTTPException(404, str(e))
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except MeetIntegrationError as e:
            raise HTTPException(503, str(e))
        except CalendarIntegrationError as e:
            raise HTTPException(503, str(e))

    def require_calendar_request(request: Request) -> None:
        if calendar.hosted_enabled():
            return
        host = request.client.host if request.client else ""
        try:
            is_local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_local = False
        if not is_local:
            raise HTTPException(403, "Google Calendar demo access is limited to local requests.")

    @app.get("/", include_in_schema=False)
    def root():
        return {"app": "Close the Gap API", "docs": "/docs", "health": "/health"}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/events", response_model=ScheduleResult)
    def post_event(body: EventCreate, request: Request, who: str = Depends(me)):
        """The signed-in person schedules a meeting. If a key person is already out, the same flow starts at once."""
        def run():
            if body.end <= body.start:
                raise ValueError("the meeting must end after it starts")
            for attendee in body.attendees:
                svc.person(attendee.personId)
            google_event_id = None
            if calendar.status(who)["connected"]:
                require_calendar_request(request)
                google_event_id = calendar.create_event(
                    who, body.title.strip() or "Untitled meeting", body.description,
                    body.start, body.end, body.attendees,
                )
            try:
                event, created = svc.schedule_meeting(
                    who, body.title, body.description, body.start, body.end, body.attendees, google_event_id,
                )
            except (LookupError, ValueError, PermissionError):
                if google_event_id:
                    calendar.delete_event(who, google_event_id)
                raise
            return ScheduleResult(eventId=event.id,
                                  calendarProvider="google" if event.googleEventId else "demo",
                                  affected=[svc._view(i, who) for i in created])
        return guard(run)

    @app.post("/events/{event_id}/attendees", response_model=list[MeetingItem])
    def post_attendee(event_id: str, body: AttendeeAdd, request: Request, who: str = Depends(me)):
        event = svc.calendar.get(event_id)
        if event and event.googleEventId:
            require_calendar_request(request)
        return guard(lambda: [svc._view(i, who) for i in svc.add_attendee(event_id, who, body.personId, body.optional)])

    @app.get("/settings/public")
    def public_settings():
        """The few settings the web app shows or uses, so the screen never disagrees with config/settings.toml."""
        return {"pastDays": S.visibility.past_days, "suddenNoticeHours": S.absence.sudden_notice_hours,
                "refreshWhileAnalysingSeconds": S.ai.refresh_while_analysing_seconds,
                "messageHideSeconds": S.ui.message_hide_seconds}

    @app.get("/data-mode")
    def get_data_mode(request: Request):
        mode = "firestore" if isinstance(svc.store, FirestoreStore) else "memory"
        admin_email = getattr(request.state, "email", "").casefold()
        return {
            "enabled": mode_registry is not None,
            "mode": mode,
            "canSwitch": mode_registry is not None and admin_email in config.data_mode_admin_emails(),
        }

    @app.post("/data-mode")
    def set_data_mode(body: DataModeRequest, request: Request):
        nonlocal svc, meet, calendar
        if mode_registry is None:
            raise HTTPException(404, "The data mode selector is disabled.")
        email = getattr(request.state, "email", "").casefold()
        if email not in config.data_mode_admin_emails():
            raise HTTPException(403, "Only an authorized demo presenter can change the app-wide data mode.")
        current_mode = "firestore" if isinstance(svc.store, FirestoreStore) else "memory"
        if body.mode != current_mode:
            next_service = build_service(mode=body.mode)
            mode_registry.set(body.mode)
            svc = next_service
            meet = GoogleMeetIntegration(svc.store, svc.calendar)
            calendar = GoogleCalendarIntegration(svc.store)
            svc.google_calendar = calendar
        return {"enabled": True, "mode": body.mode, "canSwitch": True}

    @app.get("/people")
    def people():
        return svc.store.people()

    @app.get("/directory", response_model=list[DirectoryEntry])
    def directory(q: str = "", day: Optional[date] = None, who: str = Depends(me)):
        """Search the company directory (email first, also name, title, team) for a proxy. Individuals only.
        Pass the meeting day to learn who is out of office that day."""
        return svc.directory(q, day)

    @app.get("/me", response_model=MeResponse)
    def get_me(who: str = Depends(me)):
        return MeResponse(person=svc.person(who), counts=svc.counts(who))

    @app.get("/absences", response_model=list[Absence])
    def get_absences(mine: bool = True, who: str = Depends(me)):
        return svc.absences_for(who)

    @app.post("/absences", response_model=Absence)
    def post_absence(body: AbsenceCreate, who: str = Depends(me)):
        return guard(lambda: svc.create_absence(body.personId, body.start, body.end, AbsenceSource.manual, who))

    @app.get("/items", response_model=None)
    def get_items(mode: str = Query(pattern="^(attendee|organizer|past)$"), who: str = Depends(me)
                  ) -> Union[AttendeeItems, list[MeetingItem]]:
        if mode == "attendee":
            return svc.attendee_items(who)
        return svc.organizer_items(who) if mode == "organizer" else svc.past_items(who)

    @app.get("/organizer/meetings", response_model=list[OrganizerMeeting])
    def get_organizer_meetings(who: str = Depends(me)):
        """Organizer Mode: one card per meeting, naming everyone who is out (Decision 55)."""
        return svc.organizer_meetings(who)

    @app.post("/meetings/{event_id}/action", response_model=Optional[OrganizerMeeting])
    def post_meeting_action(event_id: str, body: MeetingActionRequest, who: str = Depends(me)):
        """The organizer decides for the whole meeting: reschedule, cancel or proceed_without."""
        return guard(lambda: svc.apply_meeting_action(event_id, who, body.action))

    @app.post("/items/{item_id}/action", response_model=MeetingItem)
    def post_action(item_id: str, body: ActionRequest, request: Request, who: str = Depends(me)):
        item = svc.store.get_item(item_id)
        if item:
            event = svc.calendar.get(item.event.calendarEventId)
            if event and event.googleEventId:
                require_calendar_request(request)
        return guard(lambda: svc.apply_action(item_id, who, body.action, body.proxyId, body.note, body.noteFromAi))

    @app.get("/items/{item_id}/notes", response_model=list[Note])
    def get_meeting_notes(item_id: str, who: str = Depends(me)):
        return guard(lambda: svc.meeting_notes(item_id, who))

    @app.post("/items/{item_id}/notes", response_model=Note)
    def post_meeting_note(item_id: str, body: NoteCreate, who: str = Depends(me)):
        return guard(lambda: svc.add_meeting_note(item_id, who, body.text, body.sharedWith))

    @app.get("/integrations/google-meet/status")
    def get_google_meet_status(who: str = Depends(me)):
        return meet.status(who)

    @app.get("/integrations/google-meet/authorize")
    def authorize_google_meet(who: str = Depends(me)):
        return guard(lambda: {"authorizationUrl": meet.authorization_url(who)})

    @app.get("/integrations/google-meet/callback", include_in_schema=False)
    def google_meet_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
        destination = f"{config.web_app_url()}?meet="
        if error or not code or not state:
            return RedirectResponse(destination + "error", status_code=303)
        try:
            meet.finish_authorization(code, state)
        except MeetIntegrationError:
            return RedirectResponse(destination + "error", status_code=303)
        return RedirectResponse(destination + "connected", status_code=303)

    @app.get("/integrations/google-calendar/status")
    def get_google_calendar_status(who: str = Depends(me)):
        return calendar.status(who)

    @app.get("/integrations/google-calendar/authorize")
    def authorize_google_calendar(request: Request, who: str = Depends(me)):
        require_calendar_request(request)
        return guard(lambda: {"authorizationUrl": calendar.authorization_url(who)})

    @app.get("/integrations/google-calendar/callback", include_in_schema=False)
    def google_calendar_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None,
                                error: Optional[str] = None):
        destination = f"{config.web_app_url()}?calendar="
        if error or not code or not state:
            return RedirectResponse(destination + "error", status_code=303)
        try:
            require_calendar_request(request)
            calendar.finish_authorization(code, state)
        except (CalendarIntegrationError, HTTPException):
            return RedirectResponse(destination + "error", status_code=303)
        return RedirectResponse(destination + "connected", status_code=303)

    @app.post("/integrations/google-calendar/sync")
    def sync_google_calendar(request: Request, who: str = Depends(me)):
        require_calendar_request(request)
        def run():
            now = svc.now()
            events = calendar.list_events(who, now - timedelta(days=30), now + timedelta(days=365))
            return svc.sync_google_events(who, events)
        return guard(run)

    @app.get("/items/{item_id}/meet", response_model=MeetStatus)
    def get_meeting_meet_status(item_id: str, who: str = Depends(me)):
        return guard(lambda: meet.meeting_status(item_id, who))

    @app.put("/items/{item_id}/meet", response_model=MeetStatus)
    def put_meeting_meet_link(item_id: str, body: MeetLinkUpdate, who: str = Depends(me)):
        return guard(lambda: (
            meet.link_meeting(item_id, who, body.meetUrl),
            meet.meeting_status(item_id, who),
        )[1])

    @app.post("/items/{item_id}/meet/import", response_model=Note)
    def import_meet_transcript(item_id: str, body: TranscriptImportRequest, who: str = Depends(me)):
        return guard(lambda: meet.import_transcript(item_id, who, body.sharedWith))

    @app.get("/items/{item_id}/note-draft/available", response_model=NoteDraftAvailable)
    def get_note_draft_available(item_id: str, proxyId: Optional[str] = None, who: str = Depends(me)):
        return guard(lambda: svc.note_draft_available(item_id, who, proxyId))

    @app.post("/items/{item_id}/note-draft", response_model=NoteDraft)
    def post_note_draft(item_id: str, proxyId: Optional[str] = None, who: str = Depends(me)):
        return guard(lambda: svc.note_draft(item_id, who, proxyId))

    @app.get("/items/{item_id}/proxy-candidates", response_model=list[ProxyCandidate])
    def get_candidates(item_id: str, who: str = Depends(me)):
        return guard(lambda: svc.proxy_candidates(item_id, who))

    @app.get("/items/{item_id}/proposed-time", response_model=ProposedTime)
    def get_proposed(item_id: str, who: str = Depends(me)):
        return guard(lambda: svc.proposed_time(item_id, who))

    @app.post("/items/{item_id}/reschedule", response_model=MeetingItem)
    def post_reschedule(item_id: str, request: Request, who: str = Depends(me)):
        from .models import Action
        item = svc.store.get_item(item_id)
        if item:
            event = svc.calendar.get(item.event.calendarEventId)
            if event and event.googleEventId:
                require_calendar_request(request)
        return guard(lambda: svc.apply_action(item_id, who, Action.reschedule))

    @app.get("/proxy-requests", response_model=list[ProxyRequestView])
    def get_proxy_requests(mine: bool = True, past: bool = False, who: str = Depends(me)):
        return svc.proxy_requests_for(who, past=past)

    @app.post("/proxy-requests/{req_id}/respond", response_model=ProxyRequest)
    def post_respond(req_id: str, body: RespondRequest, who: str = Depends(me)):
        return guard(lambda: svc.respond_proxy(req_id, who, body.response))

    @app.get("/history", response_model=list[HistoryEvent])
    def get_history(mine: bool = True, who: str = Depends(me)):
        return svc.history_for(who)

    @app.get("/metrics", response_model=Metrics)
    def get_metrics():
        return svc.metrics()

    # ---- demo / ops helpers (not for production) ----
    @app.post("/dev/simulate-leave-system", response_model=Absence)
    def simulate_leave_system(body: LeaveSystemRequest):
        if config.firebase_auth_enabled():
            raise HTTPException(404, "This demo-only endpoint is disabled.")
        return guard(lambda: svc.create_absence(body.personId, body.start, body.end,
                                                AbsenceSource.leave_system, body.personId))

    @app.get("/dev/outbox")
    def outbox():
        if config.firebase_auth_enabled():
            raise HTTPException(404, "This demo-only endpoint is disabled.")
        return notify.OUTBOX

    @app.post("/dev/reset-demo")
    def reset_demo():
        """Back to the demo data, with an empty AI cache, so every card is analysed again (the "Reset demo" button)."""
        if config.firebase_auth_enabled():
            raise HTTPException(404, "This demo-only endpoint is disabled.")
        if isinstance(svc.store, FirestoreStore):
            raise HTTPException(404, "Reset is disabled for the persistent Firestore demo.")
        from .seed import build_service
        build_service(into=svc)
        return {"ok": True}

    @app.post("/jobs/run-reminders")
    def run_reminders():
        """Cloud Scheduler will call this on a schedule."""
        return {"reminders_sent": svc.run_reminders()}

    return app


app = create_app()
