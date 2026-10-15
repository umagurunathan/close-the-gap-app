"""The app's logic. Everything the API endpoints do lives here, so it can be tested without a web server."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from time import monotonic
from typing import Optional

from agents.note_drafter import draft_note
from agents.orchestrator import ai_needed, analyze
from agents.fallback.candidate_order import rank_proxies

from . import config, notify
from .calendar import SimCalendar
from .models import (
    AiResult, Absence, AbsenceSource, AbsenceType, Action, AttendeeItems, CalEvent, Counts, DirectoryEntry,
    EventAttendee, EventRef,
    HistoryEvent, ItemKind, ItemStatus, MeetingItem, Metrics, NoteDraft, NoteDraftAvailable, OrganizerMeeting, Person,
    ProposedTime, ProxyCandidate,
    ProxyRequest, ProxyRequestStatus, ProxyRequestView,
)
from .roles import is_invited_as_optional, required_ids
from .scheduling import find_slot
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
log = logging.getLogger("close_the_gap.service")
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
        # Background analysis: cards are answered at once with the rules' suggestion ("AI analysing…") while the
        # AI works in a small pool of threads; the web app checks again until every card has its final answer.
        self._lock = threading.Lock()
        self._pending: dict[tuple, float] = {}                                  # key -> when the analysis started
        self._failed: dict[tuple, tuple[float, tuple[ItemKind, AiResult]]] = {}  # key -> when it failed, fallback shown
        self._pool: Optional[ThreadPoolExecutor] = None
        self.replaying = False   # True while the seed replays a past week: no background AI for those cards

    def _cache_key(self, item: MeetingItem, e, visible) -> tuple:
        # Same meeting + same summaries this viewer can read + same AI setup = same answer, so it is reused and the AI
        # is not asked again. Any change to the meeting or its summaries makes a new key, so the AI looks again.
        return (item.id,
                (e.title, e.description, e.start.isoformat(), e.organizerId,
                 tuple((a.personId, a.optional) for a in e.attendees)),
                tuple((n.docId, n.modifiedAt.isoformat()) for n in visible),
                (S.ai.enabled, S.ai.model, S.ai.engine))

    @staticmethod
    def _is_final(result: tuple[ItemKind, AiResult]) -> bool:
        """Keep only a final answer: Gemini's (or a large-event policy answer) when the AI is on, the rules' when it is
        off. A fallback or a placeholder is not kept, so the AI is asked again later."""
        return result[1].engine in (("gemini_adk", "gemini", "rules_policy") if S.ai.enabled else ("rules",))

    def _analyze(self, item: MeetingItem, viewer: str, allow_ai: bool = True) -> tuple[ItemKind, AiResult]:
        e = self.calendar.get(item.event.calendarEventId)
        visible = self.calendar.visible_notes(e, viewer)
        key = self._cache_key(item, e, visible)
        if key in self._analysis_cache:
            return self._analysis_cache[key]
        absent = self.person(item.absentPersonId)
        run = lambda use_ai: analyze(e, absent, viewer, self.people_map(), self.calendar, self._is_out,  # noqa: E731
                                     use_ai=use_ai)
        if not (S.ai.enabled and allow_ai and S.ai.background and ai_needed(e, absent, visible)):
            result = run(allow_ai)   # AI off, card creation, tests, or a large event the rules handle: answer now
            if self._is_final(result):
                self._analysis_cache[key] = result
                self._maybe_raise(item.id, viewer, *result)
            return result

        clock = monotonic()
        with self._lock:
            failed = self._failed.get(key)
            if failed and clock - failed[0] < S.ai.retry_after_failure_seconds:
                return failed[1]       # the AI failed a moment ago: show the fallback, do not ask again yet
            started = self._pending.get(key)
            if started is None:
                started = self._pending[key] = clock
                self._background().submit(self._analyze_in_background, key, run, item.id, viewer)
        # Answer now with the rules' suggestion, labelled; the web app asks again until the AI's answer is in.
        kind, ai = run(False)
        ai = ai.model_copy()
        if clock - started < S.ai.analysing_label_max_seconds:
            ai.engine = "analysing"
        else:
            ai.engine = "rules_fallback"
            ai.checks = ["the AI is taking longer than usual. The rule-based suggestion is shown until it answers"]
        return kind, ai

    def _background(self) -> ThreadPoolExecutor:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=S.ai.background_workers, thread_name_prefix="ai-analysis")
        return self._pool

    def _analyze_in_background(self, key: tuple, run, item_id: str, viewer: str) -> None:
        try:
            result = run(True)
        except Exception as err:   # noqa: BLE001 - never let a background failure disappear silently
            log.warning("background analysis failed: %s", err)
            result = None
        with self._lock:
            self._pending.pop(key, None)
            if result and self._is_final(result):
                self._analysis_cache[key] = result
                self._failed.pop(key, None)
            elif result:
                self._failed[key] = (monotonic(), result)
        if result and self._is_final(result):
            self._maybe_raise(item_id, viewer, *result)

    def _maybe_raise(self, item_id: str, viewer: str, kind: ItemKind, ai: AiResult) -> None:
        """The AI may move a card the rules auto-handled up to "needs a decision" (`[ai] ai_may_raise_to_key_meeting`):
        a "sync" whose summaries show sign-offs, an all-hands the absent person presents at. Only upward, only from the
        absent person's own view (the view the card was classified from), only if nobody has acted on it yet."""
        if not (S.ai.ai_may_raise_to_key_meeting and kind == ItemKind.key_meeting
                and ai.engine in ("gemini", "gemini_adk")):
            return
        with self._lock:
            item = self.store.get_item(item_id)
            if (not item or viewer != item.absentPersonId or item.kind == ItemKind.key_meeting
                    or item.status != ItemStatus.auto_handled or item.decidedBy):
                return
            was = item.kind.value
            item.kind, item.status, item.chosenAction = ItemKind.key_meeting, ItemStatus.pending_decision, None
            item.updatedAt = self.now()
            self.store.save_item(item)
        self._log(item_id, "system", "ai_raised", f"the AI found this {was.replace('_', ' ')} needs a decision: {ai.reason}",
                  f"The AI found that this meeting needs a decision: {ai.reason}")

    def wait_for_analysis(self, cancel: bool = False) -> None:
        """Tests and scripts: wait until every background analysis has finished. `cancel` drops the queued ones
        (used by "Reset demo"; one already talking to Gemini is left to finish on its own)."""
        if self._pool:
            self._pool.shutdown(wait=not cancel, cancel_futures=cancel)
            self._pool = None

    # ---------- helpers ----------
    def now(self) -> datetime:
        return config.now()

    def people_map(self) -> dict[str, Person]:
        return {p.id: p for p in self.store.people()}

    def person(self, person_id: str) -> Person:
        p = self.store.get_person(person_id)
        if not p:
            raise LookupError(f"We couldn't find that person ({person_id}) in the directory.")
        return p

    def _log(self, item_id: str, actor: str, type_: str, detail: str, text: str = "") -> None:
        """`detail` is the technical record (audits); `text` is the same event in a plain sentence for the card."""
        self.store.add_history(HistoryEvent(
            id=self.store.next_id("h"), itemId=item_id, actorId=actor, type=type_, detail=detail, at=self.now(),
            text=text))

    def _first(self, person_id: str) -> str:
        return self.person(person_id).name.split()[0]

    def _decision_text(self, item: MeetingItem, caller: str, action: Action, proxy_id: Optional[str]) -> str:
        """What a person decided, in a plain sentence (activity log and emails)."""
        who, absent = self._first(caller), self._first(item.absentPersonId)
        s = item.status
        if action == Action.attend:
            return f"{who} will attend despite being out."
        if action == Action.proceed_without:
            return f"{who} chose to go ahead without {absent}." if caller != item.absentPersonId \
                else f"{who} chose to let the meeting go ahead without them."
        if action == Action.proxy:
            return (f"{who} asked {self._first(proxy_id)} to cover." if caller == item.absentPersonId
                    else f"{who} asked {self._first(proxy_id)} to cover for {absent}.")
        if s == ItemStatus.awaiting_organizer:
            return f"{who} asked the organizer to {action.value} the meeting."
        if s == ItemStatus.no_slot_found:
            return f"{who} tried to reschedule, but no time worked for everyone; the organizer will pick one."
        if s == ItemStatus.rescheduled:
            return f"{who} rescheduled the meeting to a time when everyone is back."
        if s == ItemStatus.cancelled:
            return f"{who} canceled this meeting."
        return f"{who} updated the plan for this meeting."

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
        return self.report_absence(person_id, start, end, source, entered_by)[0]

    def report_absence(self, person_id: str, start: date, end: date, source: AbsenceSource,
                       entered_by: str) -> tuple[Absence, list[MeetingItem]]:
        """Saves the absence and returns it with the cards it created (one per affected meeting)."""
        self.person(person_id)
        if end < start:
            raise ValueError("The end date must be on or after the start date.")
        absence = Absence(
            id=self.store.next_id("a"), personId=person_id, start=start, end=end, type=self.absence_type(start),
            source=source, enteredBy=entered_by, createdAt=self.now())
        self.store.add_absence(absence)
        return absence, self._scan(absence)

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
        self._log(item.id, "system", "item_created", f"{kind.value}: {ai.recommendation.value if ai.recommendation else '-'}",
                  f"{absent.name.split()[0]} is out, so this meeting was flagged"
                  + (" and handled automatically (nothing depends on them)." if kind != ItemKind.key_meeting else "."))
        if S.ai.enabled and S.ai.background and S.ai.analyse_in_background_on_creation and not self.replaying:
            self._analyze(item, absent.id)   # queued, never waited for; the AI may then raise the card (see _maybe_raise)
        return item

    # ---------- a meeting is scheduled (or changed) while a key person is already out ----------
    def schedule_meeting(self, organizer_id: str, title: str, description: str, start: datetime, end: datetime,
                         attendees: list[EventAttendee]) -> tuple[CalEvent, list[MeetingItem]]:
        """The organizer schedules a meeting. If a key person (the organizer or a required attendee) is already out
        on that day, the same flow starts right away: cards are created and the organizer gets one email."""
        self.person(organizer_id)
        if end <= start:
            raise ValueError("The meeting must end after it starts. Please check the times.")
        for a in attendees:
            self.person(a.personId)
        event = CalEvent(id=self.store.next_id("evt"), title=title.strip() or "Untitled meeting", description=description,
                         start=start, end=end, organizerId=organizer_id, attendees=attendees)
        self.calendar.add_event(event)
        self._log("-", organizer_id, "meeting_scheduled", event.title, f"{self._first(organizer_id)} scheduled the meeting.")
        return event, self._scan_event(event)

    def add_attendee(self, event_id: str, caller: str, person_id: str, optional: bool = False) -> list[MeetingItem]:
        e = self.calendar.get(event_id)
        if not e:
            raise LookupError("This meeting no longer exists. Please refresh the page to see the latest.")
        if caller != e.organizerId:
            raise PermissionError("Only the organizer can add people to this meeting.")
        self.person(person_id)
        if person_id == e.organizerId or any(a.personId == person_id for a in e.attendees):
            raise ValueError("That person is already invited to this meeting.")
        e.attendees.append(EventAttendee(personId=person_id, optional=optional))
        return self._scan_event(e, only=[person_id])

    def _scan_event(self, e: CalEvent, only: Optional[list[str]] = None) -> list[MeetingItem]:
        """Check the key people of one meeting against existing absences. One email to the organizer per call, however
        many key people are out. Optional attendees never trigger it."""
        now, day = self.now(), e.start.date()
        created: list[MeetingItem] = []
        # Every required invitee who is out gets a card. In a large event, ordinary attendees get a quiet one
        # (classified as an org-wide event); only the organizer and hosts need the organizer to act.
        for pid in dict.fromkeys([e.organizerId] + required_ids(e)):
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
            if is_invited_as_optional(e, absent.id):
                continue   # optional invitees never trigger anything
            item = self._create_item(absence, absent, e, now)
            if item:
                created.append(item)

        needs = [i for i in created if i.status == ItemStatus.pending_decision]
        if created:   # no email when nothing is affected (e.g. leave planned months ahead with no meetings yet)
            day = lambda d: f"{d.day} {d:%b}"   # noqa: E731  "20 Oct", the same format as the web app
            when = (f"on {day(absence.start)}" if absence.start == absence.end
                    else f"{day(absence.start)} – {day(absence.end)}")
            n_aff, n_dec = len(created), len(needs)
            subject = (f"You're out {when}: {n_dec} {'meeting needs' if n_dec == 1 else 'meetings need'} a decision"
                       if n_dec else f"You're out {when}: no meetings need a decision")
            body = (f"{n_aff} {'meeting is' if n_aff == 1 else 'meetings are'} affected, and "
                    f"{n_dec} {'needs' if n_dec == 1 else 'need'} your decision. Open Close the Gap to decide."
                    if n_dec else
                    f"{n_aff} {'meeting is' if n_aff == 1 else 'meetings are'} affected, and none needs your decision.")
            notify.send_email(absent.email, subject, body, now)
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
        """This person's current and upcoming absences, earliest first (an absence that has ended is not shown)."""
        today = self.now().date()
        return sorted([a for a in self.store.absences() if a.personId == person_id and a.end >= today],
                      key=lambda a: a.start)

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
        # A finished meeting is not analysed again (no AI cost, and no answer the person never saw): it shows the
        # recommendation recorded when someone decided, or the one the card was created with.
        ai = (item.aiWhenDecided or item.ai) if self._is_past(item) else self._analyze(item, viewer)[1]
        return item.model_copy(update={"ai": ai, "needsAttention": needs, "urgency": urgency,
                                       "declinedProxyIds": self._declined(item.id),
                                       "hoursToStart": round(hours, 1) if needs else None})

    def attendee_items(self, me: str) -> AttendeeItems:
        mine = sorted([self._view(i, me) for i in self.store.items()
                       if i.absentPersonId == me and not self._is_past(i)], key=lambda i: i.event.start)
        out = AttendeeItems()
        for i in mine:
            if i.status in TERMINAL:
                out.noActionNeeded.rescheduledOrCancelled.append(i)
            elif i.kind == ItemKind.team_checkin:
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

    def organizer_meetings(self, me: str) -> list[OrganizerMeeting]:
        """Organizer Mode: one card per meeting. Groups the per-person items of each meeting and gives
        one recommendation for the whole meeting."""
        groups: dict[str, list[MeetingItem]] = {}
        for i in self.organizer_items(me):
            groups.setdefault(i.event.calendarEventId, []).append(i)
        out = []
        for event_id, items in groups.items():
            items.sort(key=lambda i: self.person(i.absentPersonId).name)
            open_items = [i for i in items if i.needsAttention]
            urgency = ("urgent" if any(i.urgency == "urgent" for i in open_items)
                       else "soon" if any(i.urgency == "soon" for i in open_items) else None)
            hours = [i.hoursToStart for i in open_items if i.hoursToStart is not None]
            out.append(OrganizerMeeting(
                calendarEventId=event_id, event=items[0].event, absentees=items, ai=self._meeting_ai(items),
                needsAttention=bool(open_items), urgency=urgency, hoursToStart=min(hours) if hours else None,
                done=all(i.status in TERMINAL for i in items)))
        return sorted(out, key=lambda m: m.event.start)

    def _meeting_ai(self, items: list[MeetingItem]) -> AiResult:
        """One recommendation for the meeting, combined from each absent person's recommendation (no extra AI call):
        reschedule wins (someone is essential), then cancel, then proxy (one per person), then go on without them.
        Only people who still need a decision count, unless everyone is settled."""
        base = [i for i in items if i.needsAttention] or items
        if len(base) == 1:
            return base[0].ai.model_copy()
        order = [Action.reschedule, Action.cancel, Action.proxy, Action.proceed_without]
        pick = min(base, key=lambda i: order.index(i.ai.recommendation) if i.ai.recommendation in order else len(order))
        first = lambda i: self.person(i.absentPersonId).name.split()[0]   # noqa: E731
        engines = {i.ai.engine for i in base}
        if engines == {"gemini", "gemini_adk"}:   # all written by Gemini, some by the agent and some by one call
            engines = {"gemini"}
        if "analysing" in engines:                # the AI is still working on someone on this meeting
            engines = {"analysing"}
        return AiResult(
            recommendation=pick.ai.recommendation,
            reason=" ".join(f"{first(i)}: {i.ai.reason}" for i in base),
            confidence=pick.ai.confidence,
            sources=["each absent person's recommendation, combined"] + [s for s in pick.ai.sources if s not in ("",)],
            summariesAvailable=any(i.ai.summariesAvailable for i in base),
            needsHumanChoice=any(i.ai.needsHumanChoice for i in base),
            engine=engines.pop() if len(engines) == 1 else "mixed",
            model=pick.ai.model,
            checks=[f"{first(i)}: {c}" for i in base for c in i.ai.checks],
        )

    def apply_meeting_action(self, event_id: str, caller: str, action: Action) -> Optional[OrganizerMeeting]:
        """The organizer decides for the whole meeting: reschedule (one new time when every key person
        is back), cancel (this occurrence), or go on without them (people still undecided go ahead; any proxy or
        "I'll attend" already arranged is kept). A proxy is chosen per person, on that person's line."""
        items = [i for i in self.store.items() if i.event.calendarEventId == event_id and i.kind == ItemKind.key_meeting
                 and not self._is_past(i)]
        if not items:
            raise LookupError("This meeting no longer exists. Please refresh the page to see the latest.")
        side = set().union(*(self._organizer_side(i) for i in items))
        if caller not in side:
            raise PermissionError("Only the organizer can decide for the whole meeting.")
        if action not in (Action.reschedule, Action.cancel, Action.proceed_without):
            raise ValueError("For the whole meeting you can reschedule, cancel or go on without them. A proxy is chosen for each person.")
        open_items = [i for i in items if i.status not in TERMINAL]
        if not open_items:
            raise ValueError("This meeting has already been rescheduled or canceled, so there is nothing left to decide.")

        if action == Action.proceed_without:
            # only people with nothing arranged; a pending or accepted proxy, or "I'll attend", is kept
            undecided = {ItemStatus.pending_decision, ItemStatus.proxy_declined, ItemStatus.no_slot_found,
                         ItemStatus.awaiting_organizer}
            for i in open_items:
                if i.status in undecided:
                    self.apply_action(i.id, caller, Action.proceed_without)
        elif action == Action.cancel:
            for i in open_items:
                self.apply_action(i.id, caller, Action.cancel)
        else:
            slot = self.proposed_time(open_items[0].id)
            if slot.none:
                for i in open_items:
                    self.apply_action(i.id, caller, Action.reschedule)   # records "no suitable time found"
            else:
                e = self.calendar.get(event_id)
                self.calendar.move_event(e.id, slot.proposedStart)   # ONE move for everyone
                now = self.now()
                for i in open_items:
                    self._withdraw_requests(i, tell_accepted=False)
                    i.originalStart = i.originalStart or i.event.start
                    i.event.start, i.event.end = e.start, e.end
                    i.rescheduledTo, i.status, i.chosenAction = slot.proposedStart, ItemStatus.rescheduled, Action.reschedule
                    i.decidedBy, i.updatedAt = caller, now
                    self.store.save_item(i)
                    self._log(i.id, caller, "action_chosen", f"reschedule (whole meeting) => rescheduled to {slot.proposedStart}",
                              f"{self._first(caller)} rescheduled the meeting to a time when everyone is back.")
        return next((m for m in self.organizer_meetings(caller) if m.calendarEventId == event_id), None)

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
        listed_org = [m for m in self.organizer_meetings(me) if not m.done]   # one card per meeting; "Done" not counted
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

    def _draft_notes(self, item: MeetingItem, caller: str, proxy_id: Optional[str]):
        """The summaries an AI-drafted note for this proxy may use: those the sender can open AND the chosen proxy can
        open, so the note cannot reveal anything the proxy may not read. Returns (event, notes, reason); the reason says in plain words why no draft is possible."""
        if caller not in ({item.absentPersonId} | self._organizer_side(item)):
            raise PermissionError("Only the person who is out or the organizer can do this.")
        e = self.calendar.get(item.event.calendarEventId)
        if not proxy_id:
            return e, [], "Choose a proxy first. A draft is offered when they can open the meeting summary."
        mine = self.calendar.visible_notes(e, caller)
        if not mine:
            return e, [], "No meeting summary is available to you for this meeting, so there is nothing to draft from."
        theirs = {n.docId for n in self.calendar.visible_notes(e, proxy_id)}
        shared = [n for n in mine if n.docId in theirs]
        if not shared:
            return e, [], (f"The meeting summary isn't shared with {self.person(proxy_id).name}, so a draft could "
                           f"reveal it. Please type your own note.")
        return e, shared, None

    def note_draft_available(self, item_id: str, caller: str, proxy_id: Optional[str] = None) -> NoteDraftAvailable:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("This meeting card no longer exists. Please refresh the page to see the latest.")
        _, notes, reason = self._draft_notes(item, caller, proxy_id)
        return NoteDraftAvailable(available=bool(notes), reason=reason)

    def note_draft(self, item_id: str, caller: str, proxy_id: Optional[str] = None) -> NoteDraft:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("This meeting card no longer exists. Please refresh the page to see the latest.")
        e, notes, reason = self._draft_notes(item, caller, proxy_id)
        if not notes:
            raise ValueError(reason)
        text, engine = draft_note(e, self.person(item.absentPersonId), notes, self.person(proxy_id),
                                  organizer=self.store.get_person(e.organizerId))
        return NoteDraft(draft=text, engine=engine, model=S.ai.model if engine == "gemini" else None)

    def apply_action(self, item_id: str, caller: str, action: Action, proxy_id: Optional[str] = None,
                     note: Optional[str] = None, note_from_ai: bool = False) -> MeetingItem:
        item = self.store.get_item(item_id)
        if not item:
            raise LookupError("This meeting card no longer exists. Please refresh the page to see the latest.")
        if item.status in TERMINAL:
            raise ValueError(f"This meeting has already been {item.status.value}, so it can't be changed any more.")
        e = self.calendar.get(item.event.calendarEventId)
        organizer_side = self._organizer_side(item)
        is_organizer = caller in organizer_side
        # Who may act: BOTH the absent person and the organizer side, for planned and sudden absences.
        may_act = {item.absentPersonId} | organizer_side
        if caller not in may_act:
            raise PermissionError("Only the person who is out or the organizer can do this.")
        previous_decider, previous_status = item.decidedBy, item.status
        now = self.now()
        # What the decider was shown as the recommendation, kept to count how often recommendations are followed.
        # Read from the cache when possible; never waits for the AI.
        shown = self._analysis_cache.get(self._cache_key(item, e, self.calendar.visible_notes(e, caller)))
        shown_ai = shown[1] if shown else item.ai
        item.recommendedWhenDecided = shown_ai.recommendation
        item.aiWhenDecided = shown_ai.model_copy(deep=True)
        note_log = None

        if action == Action.attend:
            if item.ownerRole != "leaver" or caller != item.absentPersonId:
                raise ValueError("Only the person on planned leave can choose \"I'll attend\" for their own meeting.")
            item.status, item.chosenAction = ItemStatus.attending, action
            notify.send_email(self.person(item.event.organizerId).email,
                              f"FYI: {self.person(item.absentPersonId).name} will still attend '{item.event.title}'",
                              "No action needed.", now)

        elif action == Action.proceed_without:
            item.status, item.chosenAction = ItemStatus.proceeding_without, action

        elif action == Action.proxy:
            if not proxy_id:
                raise ValueError("Please choose who should cover the meeting.")
            # The proxy can be anyone in the company directory, invited or not. No organizer permission is needed
            # (forwarding an invite is allowed); the history log records who brought them in. Covering is still the
            # proxy's own choice: they are on the invite either way and may decline the proxy role.
            proxy_person = self.store.get_person(proxy_id)
            if not proxy_person or proxy_person.isGroup or proxy_id == item.absentPersonId:
                raise ValueError("Please choose one person from the company directory, other than the person who is out.")
            if self._is_out(proxy_id, item.event.start.date()):
                raise ValueError(f"{proxy_person.name} is out of office that day. Please choose someone else.")
            invited = proxy_id in self._invitee_ids(item)
            if note_from_ai:
                _, shared, reason = self._draft_notes(item, caller, proxy_id)
                if not shared:   # the note started as an AI draft from a summary this proxy may not read
                    raise ValueError(f"This note started as an AI draft. {reason}")
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
            # logged after the decision itself (below), so the activity reads in order
            note_log = ("note sent" + (" (started as an AI draft)" if note_from_ai else "") if note else "no note",
                        ("A handover note was sent with the request" + (" (started as an AI draft)." if note_from_ai else ".")
                         if note else "The request was sent without a note."))
            item.status, item.chosenAction, item.chosenProxyId = ItemStatus.proxy_requested, action, proxy_id

        elif action in (Action.reschedule, Action.cancel):
            if not is_organizer:
                # Only the organizer can change the meeting; the choice becomes a task for them.
                item.status, item.chosenAction = ItemStatus.awaiting_organizer, action
                notify.send_email(self.person(item.event.organizerId).email,
                                  f"{self.person(item.absentPersonId).name} suggests you {action.value} '{item.event.title}'",
                                  "Open Organizer Mode to do it in one click.", now)
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
                    item.originalStart = item.originalStart or item.event.start
                    item.event.start, item.event.end = e.start, e.end
                    item.rescheduledTo = slot.proposedStart
                    item.status = ItemStatus.rescheduled  # the calendar itself notifies attendees

        if action != Action.proxy and item.status in (
                ItemStatus.attending, ItemStatus.proceeding_without, ItemStatus.cancelled, ItemStatus.rescheduled):
            self._withdraw_requests(item, tell_accepted=False)  # the plan no longer needs a proxy
        item.decidedBy = caller
        item.updatedAt = now
        self.store.save_item(item)
        self._log(item.id, caller, "action_chosen", f"{action.value}{' -> ' + proxy_id if proxy_id else ''} => {item.status.value}",
                  self._decision_text(item, caller, action, proxy_id))
        if note_log:
            self._log(item.id, caller, "proxy_note", *note_log)
        # If someone changes a decision the other side already made, tell them (no email otherwise).
        if (previous_decider and previous_decider != caller and previous_decider in may_act
                and previous_status not in (ItemStatus.pending_decision, ItemStatus.auto_handled)):
            notify.send_email(self.person(previous_decider).email,
                              f"{self.person(caller).name} changed the decision for '{item.event.title}'",
                              self._decision_text(item, caller, action, proxy_id), now)
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
            raise LookupError("This meeting card no longer exists. Please refresh the page to see the latest.")
        e = self.calendar.get(item.event.calendarEventId)
        return find_slot(e, self.calendar, self.store.absences(), self.now(), people=self.people_map())

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
        self._log(item.id, req.requestedBy, "proxy_added_to_meeting", f"{proxy.name} added as an attendee",
                  f"{proxy.name.split()[0]} was added to the meeting as an optional attendee.")

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
            raise LookupError("This meeting card no longer exists. Please refresh the page to see the latest.")
        e = self.calendar.get(item.event.calendarEventId)
        notes = self.calendar.visible_notes(e, caller)
        ranked = rank_proxies(e, self.person(item.absentPersonId), self.people_map(), notes)
        ai = self._view(item, caller).ai            # the recommendation this caller sees (cached; no new AI call)
        choice = {ai.suggestedProxyId: "first", ai.backupProxyId: "second"}
        declined = set(self._declined(item.id))
        return [ProxyCandidate(personId=r["personId"], rank=r["rank"], reason=r["reason"],
                               choice=choice.get(r["personId"]), declined=r["personId"] in declined) for r in ranked]

    def active_people(self) -> list[str]:
        """Who has something to see right now: out (Attendee Mode), organizing an affected meeting (Organizer Mode),
        asked to cover (Proxy Requests), or a recent meeting in Past. Read from the stored data only (no AI call).
        The "Signed in as" list shows just these, so nobody picks a person with an empty screen."""
        ids: set[str] = set()
        for i in self.store.items():
            if self._is_past(i) and not self._recent_past(i):
                continue
            ids.add(i.absentPersonId)
            if i.kind == ItemKind.key_meeting:
                ids |= self._organizer_side(i)
        for r in self.store.proxy_requests():
            item = self.store.get_item(r.itemId)
            if item and (not self._is_past(item) or self._recent_past(item)):
                ids.add(r.proxyId)
        people = self.people_map()
        return sorted((pid for pid in ids if pid in people and not people[pid].isGroup), key=lambda pid: people[pid].name)

    def _declined(self, item_id: str) -> list[str]:
        """Who declined to cover this card, in the order they declined. A fact, so no AI is needed after a decline."""
        reqs = sorted((r for r in self.store.proxy_requests()
                       if r.itemId == item_id and r.status == ProxyRequestStatus.declined),
                      key=lambda r: r.respondedAt or r.createdAt)
        return list(dict.fromkeys(r.proxyId for r in reqs))

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
            raise LookupError("This proxy request no longer exists. Please refresh the page to see the latest.")
        if caller != req.proxyId:
            raise PermissionError("Only the person who was asked to cover can answer this request.")
        if req.status == response:
            return req      # the same answer again (a double click): already recorded, nothing to do
        if req.status != ProxyRequestStatus.pending:
            raise ValueError("You've already answered this request.")
        if response not in (ProxyRequestStatus.accepted, ProxyRequestStatus.declined):
            raise ValueError("Please choose Accept or Decline.")
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
        self._log(item.id, caller, "proxy_response", response.value,
                  f"{self._first(caller)} {'accepted and will cover' if response == ProxyRequestStatus.accepted else 'declined to cover'} the meeting.")
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
                notify.send_email(self.person(pid).email, f"Reminder: the request to cover '{item.event.title}' is still unanswered",
                                  "If it stays unanswered, the organizer will decide.", now)
            r.remindersSent += 1
            self.store.save_proxy_request(r)
            sent += 1
        # Under-24-hour alert: if a meeting starting within 24 hours still needs someone to act
        # (not handled, proxy unanswered, waiting on the organizer, proxy declined, no slot found), the organizer is
        # emailed once. This is the only email organizers get for planned leave besides asks.
        # One email per meeting, naming everyone who is out.
        due: dict[tuple[str, str], list[MeetingItem]] = {}
        for i in self.store.items():
            if i.kind != ItemKind.key_meeting or i.organizerAlerted or i.status not in ATTENTION:
                continue
            until = i.event.start - now
            if timedelta(0) < until <= timedelta(hours=S.reminders.organizer_alert_hours):
                due.setdefault((i.event.calendarEventId, self.organizer_decider(i)), []).append(i)
        for (_, decider), group in due.items():
            names = sorted(self.person(i.absentPersonId).name for i in group)
            who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            notify.send_email(self.person(decider).email,
                              f"Unresolved: '{group[0].event.title}' starts within {S.reminders.organizer_alert_hours} hours "
                              f"and {who} {'is' if len(names) == 1 else 'are'} out",
                              "Open Organizer Mode to decide.", now)
            for i in group:
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

    @staticmethod
    def _in_window(day: date, start: Optional[date], end: Optional[date]) -> bool:
        return (start is None or day >= start) and (end is None or day <= end)

    @staticmethod
    def _overlaps(a_start: date, a_end: date, start: Optional[date], end: Optional[date]) -> bool:
        return (end is None or a_start <= end) and (start is None or a_end >= start)

    def metrics(self, start: Optional[date] = None, end: Optional[date] = None) -> Metrics:
        """The impact band. Every number and which statuses count are in [metrics] in config/settings.toml.
        With `start`/`end`, only meetings in that window (by their original date) and absences overlapping it count.
        - Meetings with a plan: affected meetings whose card is settled (auto-handled, proxy, go on without, ...).
        - Days of notice: how long before the meeting the plan was made, on average (vs. finding out at the start).
        - Team hours saved (estimate): per settled card, the people in the meeting x the minutes that outcome saves
          each of them (e.g. a covered meeting avoids a failed start and a follow-up meeting).
        - Recommendations followed: of the decisions people made, how many matched what was recommended."""
        items = [i for i in self.store.items() if self._in_window(i.event.instanceStart.date(), start, end)]
        planned = [i for i in items if i.status.value in S.metrics.plan_statuses]
        leads = [max((i.event.instanceStart - i.updatedAt).total_seconds() / 86400, 0) for i in planned]
        per_person = S.metrics.minutes_saved_per_invitee
        minutes = sum(len(i.event.attendees) * getattr(per_person, i.status.value, 0) for i in planned)
        # still at risk: upcoming key meetings without a plan yet (people x the minutes lost if nobody acts)
        unplanned = [i for i in items if i.status.value not in S.metrics.plan_statuses
                     and i.kind == ItemKind.key_meeting and not self._is_past(i)]
        at_risk = sum(len(i.event.attendees) * S.metrics.at_risk_minutes_per_invitee for i in unplanned)
        decided = [i for i in items if i.decidedBy and i.recommendedWhenDecided and i.chosenAction]
        followed = [i for i in decided if i.chosenAction == i.recommendedWhenDecided]
        absences = [a for a in self.store.absences() if self._overlaps(a.start, a.end, start, end)]
        return Metrics(
            absencesSpotted=len(absences), teamHoursAtRisk=round(at_risk / 60, 1),
            handledAutomatically=sum(1 for i in planned if i.status == ItemStatus.auto_handled),
            meetingsWithPlan=len(planned), meetingsAffected=len(items),
            avgNoticeDays=round(sum(leads) / len(leads), 1) if leads else 0.0,
            teamHoursSaved=round(minutes / 60, 1),
            recommendationsFollowedPct=round(100 * len(followed) / len(decided)) if decided else None,
            decisionsCounted=len(decided),
            estimateNote="Estimate. For each meeting with a plan: people in the meeting × minutes saved per person — "
                         + ", ".join(f"{k.replace('_', ' ')} {v} min" for k, v in vars(per_person).items() if v)
                         + ". Baseline: without a plan, people join, wait and give up, and a covered decision needs a "
                           "follow-up meeting.")
