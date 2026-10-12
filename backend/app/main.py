"""The API. Every endpoint is listed, with its shapes, at /docs when the server runs. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

from datetime import date
from typing import Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config, notify
from .models import (
    Absence, AbsenceCreate, AbsenceSource, ActionRequest, AttendeeAdd, AttendeeItems, DirectoryEntry, EventCreate, HistoryEvent,
    LeaveSystemRequest, ScheduleResult,
    MeetingItem, MeResponse, Metrics, NoteDraft, NoteDraftAvailable, ProposedTime, ProxyCandidate,
    ProxyRequest, ProxyRequestView, RespondRequest,
)
from .seed import build_service
from .service import Service


def create_app(service: Optional[Service] = None) -> FastAPI:
    svc = service or build_service()
    app = FastAPI(title="Close the Gap API", version="0.2")
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_methods=["*"], allow_headers=["*"])

    def me(x_person_id: Optional[str] = Header(default=None)) -> str:
        """Simulated sign-in: the persona switcher sends the signed-in person's id in this header."""
        if not x_person_id or not svc.store.get_person(x_person_id):
            raise HTTPException(401, "send a valid X-Person-Id header")
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

    @app.get("/", include_in_schema=False)
    def root():
        return {"app": "Close the Gap API", "docs": "/docs", "health": "/health"}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/events", response_model=ScheduleResult)
    def post_event(body: EventCreate, who: str = Depends(me)):
        """The signed-in person schedules a meeting. If a key person is already out, the same flow starts at once."""
        def run():
            event, created = svc.schedule_meeting(who, body.title, body.description, body.start, body.end, body.attendees)
            return ScheduleResult(eventId=event.id, affected=[svc._view(i, who) for i in created])
        return guard(run)

    @app.post("/events/{event_id}/attendees", response_model=list[MeetingItem])
    def post_attendee(event_id: str, body: AttendeeAdd, who: str = Depends(me)):
        return guard(lambda: [svc._view(i, who) for i in svc.add_attendee(event_id, who, body.personId, body.optional)])

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

    @app.post("/items/{item_id}/action", response_model=MeetingItem)
    def post_action(item_id: str, body: ActionRequest, who: str = Depends(me)):
        return guard(lambda: svc.apply_action(item_id, who, body.action, body.proxyId, body.note, body.noteFromAi))

    @app.get("/items/{item_id}/note-draft/available", response_model=NoteDraftAvailable)
    def get_note_draft_available(item_id: str, proxyId: Optional[str] = None, who: str = Depends(me)):
        return guard(lambda: NoteDraftAvailable(available=svc.note_draft_available(item_id, who, proxyId)))

    @app.post("/items/{item_id}/note-draft", response_model=NoteDraft)
    def post_note_draft(item_id: str, proxyId: Optional[str] = None, who: str = Depends(me)):
        return guard(lambda: NoteDraft(draft=svc.note_draft(item_id, who, proxyId)))

    @app.get("/items/{item_id}/proxy-candidates", response_model=list[ProxyCandidate])
    def get_candidates(item_id: str, who: str = Depends(me)):
        return guard(lambda: svc.proxy_candidates(item_id, who))

    @app.get("/items/{item_id}/proposed-time", response_model=ProposedTime)
    def get_proposed(item_id: str, who: str = Depends(me)):
        return guard(lambda: svc.proposed_time(item_id))

    @app.post("/items/{item_id}/reschedule", response_model=MeetingItem)
    def post_reschedule(item_id: str, who: str = Depends(me)):
        from .models import Action
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
        return guard(lambda: svc.create_absence(body.personId, body.start, body.end,
                                                AbsenceSource.leave_system, body.personId))

    @app.get("/dev/outbox")
    def outbox():
        return notify.OUTBOX

    @app.post("/jobs/run-reminders")
    def run_reminders():
        """Cloud Scheduler will call this on a schedule."""
        return {"reminders_sent": svc.run_reminders()}

    return app


app = create_app()
