"""The app's logic. Everything the API endpoints do lives here, so it can be tested without a web server."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from agents.note_drafter import draft_note
from agents.orchestrator import analyze
from agents.proxy_ranker import rank_proxies

from . import config, notify
from .calendar import SimCalendar
from .models import (
    AiResult, Absence, AbsenceSource, AbsenceType, Action, AttendeeItems, CalEvent, Counts, DirectoryEntry,
    EventAttendee, EventRef,
    HistoryEvent, ItemKind, ItemStatus, MeetingItem, Metrics, Person, ProposedTime, ProxyCandidate,
    ProxyRequest, ProxyRequestStatus, ProxyRequestView,
)
from .scheduling import find_slot, key_people
from .settings import settings as S
from .store import Store

TERMINAL = {ItemStatus.rescheduled, ItemStatus.cancelled}
RESOLVED = {
    ItemStatus.auto_handled, ItemStatus.attending, ItemStatus.proceeding_without,
    ItemStatus.proxy_accepted, ItemStatus.rescheduled, ItemStatus.cancelled,
}
MAX_PROXY_REMINDERS = S.reminders.proxy_max_reminders
# Cards that still need someone to act. Everything else is settled.
ATTENTION = {
    ItemStatus.pending_decision, ItemStatus.proxy_requested, ItemStatus.awaiting_organizer,
    ItemStatus.proxy_declined, ItemStatus.no_slot_found,
}
# The numbers below are tunable in config/settings.toml
PAST_DAYS = S.visibility.past_days            # how long a finished meeting stays visible in Past
URGENT_HOURS = S.urgency.urgent_hours          # red chip
SOON_HOURS = S.urgency.soon_hours              # amber chip
SUDDEN_NOTICE_HOURS = S.absence.sudden_notice_hours  # less notice than this = a "sudden" absence


class Service:
    def __init__(self, store: Store, calendar: SimCalendar):
        self.store = store
        self.calendar = calendar
        # Recommendations are built from what each viewer can open. The cache key is the item plus the
        # fingerprint of the summaries visible to the viewer, so two viewers who can open the same documents share
        # one result, and a changed or newly shared summary triggers a fresh analysis.
        self._analysis_cache: dict[tuple, tuple[ItemKind, AiResult]] = {}

    def _analyze(self, item: MeetingItem, viewer: str, allow_ai: bool = True) -> tuple[ItemKind, AiResult]:
        e = self.calendar.get(item.event.calendarEventId)
        visible = self.calendar.visible_notes(e, viewer)
        # Same meeting + same summaries this viewer can read + same AI setup = same answer, so it is reused and the AI
        # is not asked again. Any change to the meeting or its summaries makes a new key, so the AI looks again.
        key = (item.id,
               (e.title, e.description, e.start.isoformat(), e.organizerId,
                tuple((a.personId, a.optional) for a in e.attendees)),
               tuple((n.docId, n.modifiedAt.isoformat()) for n in visible),
               (S.ai.enabled, S.ai.model))
        if key in self._analysis_cache:
            return self._analysis_cache[key]
        result = analyze(e, self.person(item.absentPersonId), viewer, self.people_map(), self.calendar, self._is_out,
                         use_ai=allow_ai)
        # Keep only a "final" answer: Gemini's when the AI is on, the rules' when it is off. A fallback answer, or a
        # rule-based placeholder made while creating the card, is not kept, so the AI is asked when the card is viewed.
        if result[1].engine == ("gemini" if S.ai.enabled else "rules"):
            self._analysis_cache[key] = result
        return result

    # ---------- helpers ----------
    def now(self) -> datetime:
        return config.now()

    def people_map(self) -> dict[str, Person]:
        return {p.id: p for p in self.store.people()}

    def person(self, person_id: str) -> Person:
        p = self.store.get_person(person_id)
        if not p:
            raise LookupError(f"unknown person {person_id}")
        return p

    def _log(self, item_id: str, actor: str, type_: str, detail: str) -> None:
        self.store.add_history(HistoryEvent(
            id=self.store.next_id("h"), itemId=item_id, actorId=actor, type=type_, detail=detail, at=self.now()))

    def organizer_decider(self, item: MeetingItem) -> str:
        """Who decides an organizer-owned item. Normally the organizer; if the organizer is the absent
        person, it escalates to their manager."""
        org = item.event.organizerId
        if org == item.absentPersonId:
            return self.person(org).managerId or org
        return org

    def _decider(self, item: MeetingItem) -> str:
        return item.absentPersonId if item.ownerRole == "leaver" else self.organizer_decider(item)

    # ---------- absences ----------
    def absence_type(self, start: date) -> AbsenceType:
        """'sudden' just means less than 24 hours' notice (or already started). A sick day planned a
        month ahead is simply planned. Simplification: the day starts at 00:00 UTC."""
        notice = datetime.combine(start, time.min, tzinfo=timezone.utc) - self.now()
        return AbsenceType.sudden if notice <= timedelta(hours=SUDDEN_NOTICE_HOURS) else AbsenceType.planned

    def create_absence(self, person_id: str, start: date, end: date,
                       source: AbsenceSource, entered_by: str) -> Absence:
        self.person(person_id)
        absence = Absence(
            id=self.store.next_id("a"), personId=person_id, start=start, end=end, type=self.absence_type(start),
            source=source, enteredBy=entered_by, createdAt=self.now())
        self.store.add_absence(absence)
        self._scan(absence)
        return absence

    def _create_item(self, absence: Absence, absent: Person, e: CalEvent, now: datetime) -> Optional[MeetingItem]:
        """One card for (this meeting, this absent person), unless the meeting is over or the card already exists."""
        if e.end <= now or any(i.event.calendarEventId == e.id and i.absentPersonId == absent.id
                               for i in self.store.items()):
            return None
        owner_role = "leaver" if absence.type == AbsenceType.planned else "organizer"
        item = MeetingItem(
            id=self.store.next_id("i"), absenceId=absence.id, absentPersonId=absent.id, ownerRole=owner_role,
            event=EventRef(calendarEventId=e.id, instanceStart=e.start, title=e.title, start=e.start, end=e.end,
                           organizerId=e.organizerId, attendees=e.attendees),
            kind=ItemKind.key_meeting, ai=AiResult(),
            status=ItemStatus.pending_decision, createdAt=now, updatedAt=now)
        # The shared state (is it routine / a general event?) is judged from the ABSENT person's view of the
        # summaries, so nothing is concluded from documents they cannot open. Each viewer's own recommendation
        # is built when the item is listed (see _view).
        # With [ai] analyse_on_creation = false, the card starts with the rule-based answer so creating an absence (or
        # starting the server) never waits for the AI; Gemini is asked when the card is first viewed.
        kind, ai = self._analyze(item, absent.id, allow_ai=S.ai.analyse_on_creation)
        item.kind, item.ai = kind, ai
        if kind != ItemKind.key_meeting:
            item.status = ItemStatus.auto_handled
            item.chosenAction = Action.proceed_without
        self.store.add_item(item)
        self._log(item.id, "system", "item_created", f"{kind.value}: {ai.recommendation.value if ai.recommendation else '-'}")
        return item

    # ---------- a meeting is scheduled (or changed) while a key person is already out ----------
    def schedule_meeting(self, organizer_id: str, title: str, description: str, start: datetime, end: datetime,
                         attendees: list[EventAttendee]) -> tuple[CalEvent, list[MeetingItem]]:
        """The organizer schedules a meeting. If a key person (the organizer or a required attendee) is already out
        on that day, the same flow starts right away: cards are created and the organizer gets one email."""
        self.person(organizer_id)
        if end <= start:
            raise ValueError("the meeting must end after it starts")
        for a in attendees:
            self.person(a.personId)
        event = CalEvent(id=self.store.next_id("evt"), title=title.strip() or "Untitled meeting", description=description,
                         start=start, end=end, organizerId=organizer_id, attendees=attendees)
        self.calendar.add_event(event)
        self._log("-", organizer_id, "meeting_scheduled", event.title)
        return event, self._scan_event(event)

    def add_attendee(self, event_id: str, caller: str, person_id: str, optional: bool = False) -> list[MeetingItem]:
        e = self.calendar.get(event_id)
        if not e:
            raise LookupError("meeting not found")
        if caller != e.organizerId:
            raise PermissionError("only the organizer can add people to the meeting")
        self.person(person_id)
        if person_id == e.organizerId or any(a.personId == person_id for a in e.attendees):
            raise ValueError("that person is already invited")
        e.attendees.append(EventAttendee(personId=person_id, optional=optional))
        return self._scan_event(e, only=[person_id])

    def _scan_event(self, e: CalEvent, only: Optional[list[str]] = None) -> list[MeetingItem]:
        """Check the key people of one meeting against existing absences. One email to the organizer per call, however
        many key people are out. Optional attendees never trigger it."""
        now, day = self.now(), e.start.date()
        created: list[MeetingItem] = []
        for pid in key_people(e):
            if only is not None and pid not in only:
                continue
            absence = next((a for a in self.store.absences() if a.personId == pid and a.start <= day <= a.end), None)
            if absence:
                item = self._create_item(absence, self.person(pid), e, now)
                if item:
                    created.append(item)
        needs = [i for i in created if i.kind == ItemKind.key_meeting]
        if needs:
            names = [self.person(i.absentPersonId).name for i in needs]
            who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            notify.send_email(self.person(e.organizerId).email,
                              f"You scheduled '{e.title}' while {who} {'is' if len(names) == 1 else 'are'} out",
                              "Open Organizer Mode to reschedule, name a proxy, or go ahead.", now)
            for i in needs:           # the organizer has just been told, so the under-24-hour alert would repeat it
                i.organizerAlerted = True
                self.store.save_item(i)
        return created

    def _scan(self, absence: Absence) -> list[MeetingItem]:
        now = self.now()
        absent = self.person(absence.personId)
        created: list[MeetingItem] = []
        for e in self.calendar.events_in_window(absent.id, absence.start, absence.end):
            item = self._create_item(absence, absent, e, now)
            if item:
                created.append(item)

        needs = [i for i in created if i.status == ItemStatus.pending_decision]
        notify.send_email(
            absent.email, f"You're out {absence.start} to {absence.end}: {len(needs)} meeting(s) need a decision",
            f"{len(created)} meetings are affected; {len(needs)} need your decision. Open Close the Gap.", now)
        if absence.type == AbsenceType.sudden:
            # Sudden absence: organizers are told right away. (Planned leave: no email at creation; they see the
            # items in Organizer Mode and get the under-24-hour alert if nobody has acted.)
            for org_id in {self._decider(i) for i in needs if i.ownerRole == "organizer"}:
                notify.send_email(self.person(org_id).email,
                                  f"{absent.name} is out suddenly: meetings you organize are affected",
                                  "Open Organizer Mode to decide what to do for each meeting.", now)
            for i in needs:
                i.organizerAlerted = True
                self.store.save_item(i)
        return created

    def absences_for(self, person_id: str) -> list[Absence]:
        return sorted([a for a in self.store.absences() if a.personId == person_id], key=lambda a: a.start)

    # ---------- listing ----------
    def _is_past(self, item: MeetingItem) -> bool:
        """a meeting leaves the working tabs and moves to Past only once its time has passed."""
        return item.event.end <= self.now()

    def _recent_past(self, item: MeetingItem) -> bool:
        return self._is_past(item) and self.now() - item.event.end <= timedelta(days=PAST_DAYS)

    def _view(self, item: MeetingItem, viewer: str) -> MeetingItem:
        """The item as `viewer` sees it. Two things are added:
        - the recommendation built from the summaries THIS viewer can open, and
        - the same for everyone: does the card still need someone to act, and how close is the
          meeting? No 'who is responsible' rule: either side can act. Urgency: amber within 3 days, red within 24 hours."""
        needs = item.status in ATTENTION and not self._is_past(item)
        hours = (item.event.start - self.now()).total_seconds() / 3600
        urgency = None
        if needs and hours <= URGENT_HOURS:
            urgency = "urgent"
        elif needs and hours <= SOON_HOURS:
            urgency = "soon"
        _, ai = self._analyze(item, viewer)
        return item.model_copy(update={"ai": ai, "needsAttention": needs, "urgency": urgency,
                                       "hoursToStart": round(hours, 1) if needs else None})

    def attendee_items(self, me: str) -> AttendeeItems:
        mine = sorted([self._view(i, me) for i in self.store.items()
                       if i.absentPersonId == me and not self._is_past(i)], key=lambda i: i.event.start)
        out = AttendeeItems()
        for i in mine:
            if i.kind == ItemKind.team_checkin:
                out.noActionNeeded.teamCheckins.append(i)
            elif i.kind == ItemKind.org_event:
                out.noActionNeeded.orgEvents.append(i)
            else:
                out.needsAction.append(i)
        return out

    def organizer_items(self, me: str) -> list[MeetingItem]:
        """Meetings I organize where someone else is absent (planned or sudden), so organizers can look ahead."""
        out = []
        for i in self.store.items():
            if i.absentPersonId == me or i.kind != ItemKind.key_meeting or self._is_past(i):
                continue
            if i.event.organizerId == me or (i.ownerRole == "organizer" and self.organizer_decider(i) == me):
                out.append(self._view(i, me))
        return sorted(out, key=lambda i: i.event.start)

    def past_items(self, me: str) -> list[MeetingItem]:
        """Finished meetings (last 30 days) where I was the absent person or on the organizer side. Same cards,
        read-only in the web app. Meetings I covered as a proxy come from proxy_requests_for(me, past=True)."""
        out = []
        for i in self.store.items():
            if i.kind != ItemKind.key_meeting or not self._recent_past(i):
                continue
            if i.absentPersonId == me or me in self._organizer_side(i):
                out.append(self._view(i, me))
        return sorted(out, key=lambda i: i.event.start, reverse=True)

    def counts(self, me: str) -> Counts:
        listed_attendee = self.attendee_items(me).needsAction
        listed_org = self.organizer_items(me)
        open_attendee = [i for i in listed_attendee if i.needsAttention]
        open_org = [i for i in listed_org if i.needsAttention]
        # The number in each tab's brackets = cards listed in that tab. "N need action" = cards that are not settled.
        listed_proxy = self.proxy_requests_for(me)
        open_proxy = [v for v in listed_proxy if v.request.status == ProxyRequestStatus.pending]
        return Counts(attendee=len(listed_attendee), organizer=len(listed_org), proxyRequests=len(listed_proxy),
                      attendeeOpen=len(open_attendee), organizerOpen=len(open_org), proxyOpen=len(open_proxy))

    # ---------- actions ----------
    def _organizer_side(self, item: MeetingItem) -> set[str]:
        """The organizer, or their manager when the organizer is the absent person."""
        side = {item.event.organizerId}
        if item.ownerRole == "organizer":
            side.add(self.organizer_decider(item))
        return side

    def _openly_shared_notes(self, item: MeetingItem, caller: str):
        """summaries the host shared with EVERYONE invited (the organizer always has access). A partly
        shared summary does not count. Only notes the caller can open are considered."""
        if caller not in ({item.absentPersonId} | self._organizer_side(item)):
            raise PermissionError("only the absent person or the organizer can do this")
        e = self.calendar.get(item.event.calendarEventId)
        return e, [n for n in self.calendar.visible_notes(e, caller)
                   if all(a.personId == e.organizerId or a.personId in n.sharedWith for a in e.attendees)]

    def note_draft_available(self, item_id: str, caller: str, proxy_id: Optional[str] = None) -> bool:
        """An AI-drafted note for the proxy is offered only when the summary is openly shared with everyone invited,
        and the chosen proxy is one of them. Otherwise it is off and the sender types their own note. No reason is
        shown for why."""
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("item not found")
        if proxy_id and proxy_id not in self._invitee_ids(item):
            return False
        return bool(self._openly_shared_notes(item, caller)[1])

    def note_draft(self, item_id: str, caller: str, proxy_id: Optional[str] = None) -> str:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("item not found")
        if proxy_id and proxy_id not in self._invitee_ids(item):
            raise ValueError("an AI draft is not available for a proxy who is not on the invite")
        e, notes = self._openly_shared_notes(item, caller)
        if not notes:
            raise ValueError("an AI draft is not available for this meeting")
        return draft_note(e, self.person(item.absentPersonId), notes)

    def apply_action(self, item_id: str, caller: str, action: Action, proxy_id: Optional[str] = None,
                     note: Optional[str] = None, note_from_ai: bool = False) -> MeetingItem:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("item not found")
        if item.status in TERMINAL:
            raise ValueError(f"item is already {item.status.value}")
        e = self.calendar.get(item.event.calendarEventId)
        organizer_side = self._organizer_side(item)
        is_organizer = caller in organizer_side
        # Who may act: BOTH the absent person and the organizer side, for planned and sudden absences.
        may_act = {item.absentPersonId} | organizer_side
        if caller not in may_act:
            raise PermissionError("only the absent person or the organizer can do this")
        previous_decider, previous_status = item.decidedBy, item.status
        now = self.now()

        if action == Action.attend:
            if item.ownerRole != "leaver" or caller != item.absentPersonId:
                raise ValueError("'I'll attend' only applies to the leaver's own planned-leave items")
            item.status, item.chosenAction = ItemStatus.attending, action
            notify.send_email(self.person(item.event.organizerId).email,
                              f"FYI: {self.person(item.absentPersonId).name} will still attend '{item.event.title}'",
                              "No action needed.", now)

        elif action == Action.proceed_without:
            item.status, item.chosenAction = ItemStatus.proceeding_without, action

        elif action == Action.proxy:
            if not proxy_id:
                raise ValueError("proxyId is required when choosing a proxy")
            # The proxy can be anyone in the company directory, invited or not. No organizer permission is needed
            # (forwarding an invite is allowed); the history log records who brought them in. Covering is still the
            # proxy's own choice: they are on the invite either way and may decline the proxy role.
            proxy_person = self.store.get_person(proxy_id)
            if not proxy_person or proxy_person.isGroup or proxy_id == item.absentPersonId:
                raise ValueError("the proxy must be an individual in the company directory, and not the absent person")
            if self._is_out(proxy_id, item.event.start.date()):
                raise ValueError(f"{proxy_person.name} is out of office that day")
            invited = proxy_id in self._invitee_ids(item)
            if note_from_ai and not invited:
                raise ValueError("an AI draft is not available for a proxy who is not on the invite")
            self._withdraw_requests(item, tell_accepted=True)   # a new proxy replaces the earlier one(s)
            note = (note or "").strip() or None
            req = ProxyRequest(id=self.store.next_id("pr"), itemId=item.id, proxyId=proxy_id, requestedBy=caller,
                               note=note, addedToMeeting=not invited, createdAt=now)
            self.store.add_proxy_request(req)
            has_notes = bool(self.calendar.visible_notes(e, proxy_id))
            body = "Please accept or decline at the earliest.\n"
            body += "A link to the meeting notes is included; it opens with your own access." if has_notes \
                else "No meeting notes are open to you."
            if not invited:
                body += "\nYou have been added to the meeting as an optional attendee; the invite is on its way."
                self._add_proxy_to_meeting(item, req, now)
            if note:
                body += f"\n\nNote from {self.person(caller).name}:\n{note}"
            notify.send_email(self.person(proxy_id).email,
                              f"Can you cover '{item.event.title}' for {self.person(item.absentPersonId).name}?", body, now)
            self._log(item.id, caller, "proxy_note",
                      "note sent" + (" (started as an AI draft)" if note_from_ai else "") if note else "no note")
            item.status, item.chosenAction, item.chosenProxyId = ItemStatus.proxy_requested, action, proxy_id

        elif action in (Action.reschedule, Action.cancel):
            if not is_organizer:
                # Only the organizer can change the meeting; the choice becomes a task for them.
                item.status, item.chosenAction = ItemStatus.awaiting_organizer, action
                notify.send_email(self.person(item.event.organizerId).email,
                                  f"{self.person(item.absentPersonId).name} suggests you {action.value} '{item.event.title}'",
                                  "Open Organizer Mode: one click to proceed.", now)
            elif action == Action.cancel:
                self.calendar.cancel_event(e.id)
                item.status, item.chosenAction = ItemStatus.cancelled, action
            else:
                slot = self.proposed_time(item.id)
                item.chosenAction = action
                if slot.none:
                    item.status = ItemStatus.no_slot_found
                else:
                    self.calendar.move_event(e.id, slot.proposedStart)
                    item.event.start, item.event.end = e.start, e.end
                    item.rescheduledTo = slot.proposedStart
                    item.status = ItemStatus.rescheduled  # the calendar itself notifies attendees

        if action != Action.proxy and item.status in (
                ItemStatus.attending, ItemStatus.proceeding_without, ItemStatus.cancelled, ItemStatus.rescheduled):
            self._withdraw_requests(item, tell_accepted=False)  # the plan no longer needs a proxy
        item.decidedBy = caller
        item.updatedAt = now
        self.store.save_item(item)
        self._log(item.id, caller, "action_chosen", f"{action.value}{' -> ' + proxy_id if proxy_id else ''} => {item.status.value}")
        # If someone changes a decision the other side already made, tell them (no email otherwise).
        if (previous_decider and previous_decider != caller and previous_decider in may_act
                and previous_status not in (ItemStatus.pending_decision, ItemStatus.auto_handled)):
            notify.send_email(self.person(previous_decider).email,
                              f"{self.person(caller).name} changed the decision for '{item.event.title}'",
                              f"It is now: {item.status.value}.", now)
        return self._view(item, caller)

    def _withdraw_requests(self, item: MeetingItem, tell_accepted: bool) -> None:
        """Earlier proxy requests for this meeting no longer apply. They stay visible to the proxy as 'withdrawn'. Only someone who had already accepted is told, and only when replaced by another proxy."""
        now = self.now()
        for r in self.store.proxy_requests():
            if r.itemId != item.id or r.status not in (ProxyRequestStatus.pending, ProxyRequestStatus.accepted):
                continue
            was_accepted = r.status == ProxyRequestStatus.accepted
            r.status = ProxyRequestStatus.withdrawn
            self.store.save_proxy_request(r)
            if was_accepted and tell_accepted:   # they stay on the invite (someone chose them on purpose); only the cover role ends
                notify.send_email(self.person(r.proxyId).email,
                                  f"You no longer need to cover '{item.event.title}'",
                                  "Someone else will cover it, or the plan changed.", now)

    def proposed_time(self, item_id: str) -> ProposedTime:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("item not found")
        e = self.calendar.get(item.event.calendarEventId)
        return find_slot(e, self.calendar, self.store.absences(), self.now())

    def _invitee_ids(self, item: MeetingItem) -> set[str]:
        e = self.calendar.get(item.event.calendarEventId)
        return {a.personId for a in e.attendees} | {e.organizerId}

    def _is_out(self, person_id: str, day: date) -> bool:
        return any(a.personId == person_id and a.start <= day <= a.end for a in self.store.absences())

    def _add_proxy_to_meeting(self, item: MeetingItem, req: ProxyRequest, now: datetime) -> None:
        """A proxy who was not invited joins this one meeting as an optional attendee (so never a key person). The
        calendar sends the invite. The organizer gets one FYI unless they made the request."""
        e = self.calendar.get(item.event.calendarEventId)
        e.attendees.append(EventAttendee(personId=req.proxyId, optional=True))
        self._sync_invitees(e)
        proxy, absent = self.person(req.proxyId), self.person(item.absentPersonId)
        if req.requestedBy != e.organizerId:
            notify.send_email(self.person(e.organizerId).email,
                              f"{proxy.name} was added to '{e.title}' as a proxy for {absent.name}",
                              f"{self.person(req.requestedBy).name} named them. They can still decline to cover. No action needed.", now)
        self._log(item.id, req.requestedBy, "proxy_added_to_meeting", f"{proxy.name} added as an attendee")

    def _sync_invitees(self, e: CalEvent) -> None:
        """Keep every card's copy of the invitee list in step with the calendar."""
        for i in self.store.items():
            if i.event.calendarEventId == e.id:
                i.event.attendees = list(e.attendees)
                self.store.save_item(i)

    def directory(self, query: str = "", day: Optional[date] = None, limit: int = S.directory.max_results) -> list[DirectoryEntry]:
        """The company directory (simulated from the seed file; a real directory can be added behind this method).
        Individuals only, matched on email, name, title or department. `out` is set for people on leave that day."""
        q = query.strip().lower()
        hits = [p for p in self.store.people()
                if not p.isGroup and (not q or any(q in s.lower() for s in (p.email, p.name, p.title, p.department)))]
        return [DirectoryEntry(**p.model_dump(), out=bool(day and self._is_out(p.id, day)))
                for p in sorted(hits, key=lambda p: p.name)[:limit]]

    def proxy_candidates(self, item_id: str, caller: str) -> list[ProxyCandidate]:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("item not found")
        e = self.calendar.get(item.event.calendarEventId)
        notes = self.calendar.visible_notes(e, caller)
        ranked = rank_proxies(e, self.person(item.absentPersonId), self.people_map(), notes)
        return [ProxyCandidate(personId=r["personId"], rank=r["rank"], reason=r["reason"]) for r in ranked]

    # ---------- proxy requests ----------
    def proxy_requests_for(self, me: str, past: bool = False) -> list[ProxyRequestView]:
        """Requests addressed to me, whatever my answer (pending, accepted, declined, withdrawn), so nothing
        vanishes after I reply. They stay in the Proxy Requests tab until the meeting time has passed, then move
        to Past."""
        out = []
        for r in self.store.proxy_requests():
            if r.proxyId != me:
                continue
            item = self.store.get_item(r.itemId)
            include = self._recent_past(item) if past else not self._is_past(item)
            if not include:
                continue
            e = self.calendar.get(item.event.calendarEventId)
            out.append(ProxyRequestView(request=r, item=self._view(item, me),
                                        notesAvailable=bool(self.calendar.visible_notes(e, me))))
        return sorted(out, key=lambda v: v.item.event.start, reverse=past)

    def respond_proxy(self, req_id: str, caller: str, response: ProxyRequestStatus) -> ProxyRequest:
        req = self.store.get_proxy_request(req_id)
        if not req:
            raise LookupError("request not found")
        if caller != req.proxyId:
            raise PermissionError("only the requested proxy can answer")
        if req.status != ProxyRequestStatus.pending:
            raise ValueError("request already answered")
        if response not in (ProxyRequestStatus.accepted, ProxyRequestStatus.declined):
            raise ValueError("response must be accepted or declined")
        now = self.now()
        req.status, req.respondedAt = response, now
        self.store.save_proxy_request(req)
        item = self.store.get_item(req.itemId)
        if response == ProxyRequestStatus.accepted:
            item.status = ItemStatus.proxy_accepted  # nobody else is told
        else:
            item.status = ItemStatus.proxy_declined
            proxy = self.person(req.proxyId)
            for pid in {item.absentPersonId, item.event.organizerId}:
                notify.send_email(self.person(pid).email, f"{proxy.name} declined to cover '{item.event.title}'",
                                  "Choose another proxy or reschedule.", now)
        item.updatedAt = now
        self.store.save_item(item)
        self._log(item.id, caller, "proxy_response", response.value)
        return req

    def run_reminders(self) -> int:
        """Called on a schedule (Cloud Scheduler later). Reminds silent proxies and their organizers; never acts."""
        now, sent = self.now(), 0
        for r in self.store.proxy_requests():
            if r.status != ProxyRequestStatus.pending or r.remindersSent >= MAX_PROXY_REMINDERS:
                continue
            item = self.store.get_item(r.itemId)
            if self._is_past(item):
                continue
            for pid in {r.proxyId, item.event.organizerId}:
                notify.send_email(self.person(pid).email, f"Reminder: proxy request for '{item.event.title}' is unanswered",
                                  "The organizer decides if it stays unanswered.", now)
            r.remindersSent += 1
            self.store.save_proxy_request(r)
            sent += 1
        # Under-24-hour alert: if a meeting starting within 24 hours still needs someone to act
        # (not handled, proxy unanswered, waiting on the organizer, proxy declined, no slot found), the organizer is
        # emailed once. This is the only email organizers get for planned leave besides asks.
        for i in self.store.items():
            if i.kind != ItemKind.key_meeting or i.organizerAlerted or i.status not in ATTENTION:
                continue
            until = i.event.start - now
            if timedelta(0) < until <= timedelta(hours=S.reminders.organizer_alert_hours):
                notify.send_email(self.person(self.organizer_decider(i)).email,
                                  f"Unresolved: '{i.event.title}' starts within {S.reminders.organizer_alert_hours} hours and {self.person(i.absentPersonId).name} is out",
                                  "Open Organizer Mode to decide.", now)
                i.organizerAlerted = True
                self.store.save_item(i)
                sent += 1
        # TODO: leaver prompt cadence (weekly, then daily within 3 days).
        return sent

    # ---------- history and metrics ----------
    def history_for(self, me: str) -> list[HistoryEvent]:
        cutoff = self.now() - timedelta(days=S.visibility.history_days)
        mine_items = {i.id for i in self.store.items() if me in (i.absentPersonId, i.event.organizerId)}
        return sorted([h for h in self.store.history() if h.at >= cutoff and (h.actorId == me or h.itemId in mine_items)],
                      key=lambda h: h.at, reverse=True)

    def metrics(self) -> Metrics:
        resolved = [i for i in self.store.items() if i.status in RESOLVED]
        leads = [max((i.event.instanceStart - i.updatedAt).total_seconds() / 86400, 0) for i in resolved]
        saved = 0
        for i in resolved:
            if i.status in (ItemStatus.proxy_accepted, ItemStatus.rescheduled, ItemStatus.cancelled):
                n = len(i.event.attendees)
                saved += n * (S.metrics.minutes_lost_in_failed_meeting + S.metrics.minutes_lost_in_follow_up)
        return Metrics(meetingsResolved=len(resolved),
                       avgLeadTimeDays=round(sum(leads) / len(leads), 1) if leads else 0.0,
                       attendeeMinutesSaved=saved)
