"""Data shapes. Field names are camelCase on purpose: they are the same names the web app and the API use."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AbsenceType(str, Enum):
    planned = "planned"
    sudden = "sudden"


class AbsenceSource(str, Enum):
    calendar_ooo = "calendar_ooo"
    leave_system = "leave_system"
    manual = "manual"


class Action(str, Enum):
    attend = "attend"                    # "I'll attend"
    proceed_without = "proceed_without"  # "Go on without me"
    proxy = "proxy"
    reschedule = "reschedule"
    cancel = "cancel"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ItemKind(str, Enum):
    key_meeting = "key_meeting"      # a small group where the absence may change the outcome; a person decides
    team_checkin = "team_checkin"    # stand-ups and status syncs: go on without the person
    org_event = "org_event"          # town halls, talks, site or company-wide events sent to a large list


class ItemStatus(str, Enum):
    pending_decision = "pending_decision"
    auto_handled = "auto_handled"
    attending = "attending"
    proceeding_without = "proceeding_without"
    proxy_requested = "proxy_requested"
    proxy_accepted = "proxy_accepted"
    proxy_declined = "proxy_declined"
    awaiting_organizer = "awaiting_organizer"
    rescheduled = "rescheduled"
    cancelled = "cancelled"
    no_slot_found = "no_slot_found"


class ProxyRequestStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    withdrawn = "withdrawn"  # the sender chose someone else, or the plan changed, so the proxy is no longer needed


class WorkingHours(BaseModel):
    start: str = "09:00"
    end: str = "17:30"


class Person(BaseModel):
    id: str
    name: str
    email: str
    title: str = ""
    department: str = ""
    managerId: Optional[str] = None
    timeZone: str = "America/New_York"
    workingHours: WorkingHours = Field(default_factory=WorkingHours)
    isGroup: bool = False  # true for distribution lists / groups: never offered as a proxy


class DirectoryEntry(Person):
    out: bool = False  # on leave on the meeting day, so they cannot be named as a proxy


class OrganizerMeeting(BaseModel):
    """Organizer Mode card: ONE per meeting, naming everyone who is out. The absent people still each
    have their own card in Attendee Mode; this brings them together for the one person who decides for the meeting."""
    calendarEventId: str
    event: "EventRef"
    absentees: list["MeetingItem"] = Field(default_factory=list)   # one per absent key person, as this organizer sees it
    ai: "AiResult"                                                  # one recommendation for the whole meeting
    needsAttention: bool = False
    urgency: Optional[str] = None
    hoursToStart: Optional[float] = None
    done: bool = False   # rescheduled or cancelled for everyone: listed under "Done", not counted in the tab


class MeetingActionRequest(BaseModel):
    """An organizer's decision for the whole meeting: reschedule, cancel or proceed_without (go on without them)."""
    action: "Action"
    start: Optional[datetime] = None   # reschedule only: a time the organizer picked instead of the proposed one


class Absence(BaseModel):
    id: str
    personId: str
    start: date
    end: date
    type: AbsenceType
    source: AbsenceSource
    enteredBy: str
    createdAt: datetime


class EventAttendee(BaseModel):
    personId: str
    optional: bool = False


class EventRef(BaseModel):
    calendarEventId: str
    instanceStart: datetime
    title: str
    start: datetime
    end: datetime
    organizerId: str
    attendees: list[EventAttendee]


class AiResult(BaseModel):
    recommendation: Optional[Action] = None
    reason: str = ""
    confidence: Confidence = Confidence.low
    sources: list[str] = Field(default_factory=list)
    summariesAvailable: bool = False
    suggestedProxyId: Optional[str] = None
    backupProxyId: Optional[str] = None   # the second choice: shown on the card, suggested if the first declines
    kind: Optional[ItemKind] = None       # the kind of meeting this answer concluded (key meeting, team check-in, …)
    # What simple rules alone would have said for the same meeting (only on AI answers), so the card can show the
    # difference the AI makes: {"kind", "recommendation", "suggestedProxyId", "reason"}.
    rulesAnswer: Optional[dict] = None
    needsHumanChoice: bool = False
    fingerprint: list[dict] = Field(default_factory=list)
    # Who produced this answer: "gemini" (possibly adjusted by the checks; see `checks`), "rules" (AI switched off),
    # "rules_fallback" (the AI was unavailable) or "rules_override" (the checks rejected the AI's whole answer).
    # The card shows a green tag for Gemini and a grey one for the rules.
    engine: str = "rules"
    model: Optional[str] = None   # the Gemini model that produced the answer (engine "gemini")
    # Corrections the checking layer (agents/guard.py) made to the AI's answer, in plain words. Empty = none needed.
    checks: list[str] = Field(default_factory=list)
    # The tools the ADK agent called, in order (engine "gemini_adk"), e.g. ["get_meeting", "read_summaries"].
    toolsUsed: list[str] = Field(default_factory=list)


class MeetingItem(BaseModel):
    id: str
    absenceId: str
    absentPersonId: str
    ownerRole: str  # "leaver" | "organizer"
    event: EventRef
    kind: ItemKind
    ai: AiResult
    status: ItemStatus
    chosenAction: Optional[Action] = None
    chosenProxyId: Optional[str] = None
    rescheduledTo: Optional[datetime] = None
    originalStart: Optional[datetime] = None   # the time before the first reschedule, shown struck through
    recommendedWhenDecided: Optional[Action] = None   # the recommendation the decider saw when they acted
    aiWhenDecided: Optional[AiResult] = None          # the whole recommendation they saw (shown on Past cards, no new AI call)
    # Computed when listing (not stored); the same for every viewer:
    needsAttention: bool = False          # still needs someone to act (not settled)
    urgency: Optional[str] = None         # "soon" (<= 2 days) | "urgent" (<= 24 hours), only while needsAttention
    hoursToStart: Optional[float] = None  # hours until the meeting starts, while needsAttention
    declinedProxyIds: list[str] = Field(default_factory=list)   # who declined to cover this card (never suggested again)
    decidedBy: Optional[str] = None       # who last chose an action (absent person or organizer side)
    organizerAlerted: bool = False        # the under-24-hour alert has been sent once
    createdAt: datetime
    updatedAt: datetime


class ProxyRequest(BaseModel):
    id: str
    itemId: str
    proxyId: str
    requestedBy: str
    note: Optional[str] = None        # the sender's own note to the proxy (optional; may start from an AI draft)
    addedToMeeting: bool = False      # the proxy was not invited, so they were added to the meeting when asked (they stay on the invite whatever happens next)
    status: ProxyRequestStatus = ProxyRequestStatus.pending
    remindersSent: int = 0
    createdAt: datetime
    respondedAt: Optional[datetime] = None


class HistoryEvent(BaseModel):
    id: str
    itemId: str
    actorId: str
    type: str
    detail: str            # technical record, for audits
    at: datetime
    text: str = ""         # the same event in a plain sentence, shown on the card ("Priya asked Meena to cover.")


# ---- Simulated calendar (stands in for Google Calendar + shared notes) ----

class Note(BaseModel):
    """A meeting summary / notes doc. Only readable by people it is shared with (and the organizer)."""
    docId: str
    modifiedAt: datetime
    text: str
    sharedWith: list[str] = Field(default_factory=list)
    source: Optional[str] = None
    sourceId: Optional[str] = None


class NoteCreate(BaseModel):
    text: str
    sharedWith: list[str] = Field(default_factory=list)


class MeetLinkUpdate(BaseModel):
    meetUrl: str


class TranscriptImportRequest(BaseModel):
    sharedWith: list[str] = Field(default_factory=list)


class MeetStatus(BaseModel):
    meetUrl: Optional[str] = None
    configured: bool
    connected: bool


class CalEvent(BaseModel):
    id: str
    seriesId: Optional[str] = None
    title: str
    description: str = ""
    start: datetime
    end: datetime
    organizerId: str
    attendees: list[EventAttendee]
    inviteGroup: Optional[str] = None  # set when the invite goes to a group / distribution list
    meetUrl: Optional[str] = None
    googleEventId: Optional[str] = None
    googleCalendarOwnerId: Optional[str] = None
    notes: list[Note] = Field(default_factory=list)
    cancelled: bool = False


# ---- Request / response bodies ----

class AbsenceCreate(BaseModel):
    """The type (planned or sudden) is not sent: the server works it out from the notice given."""
    personId: str
    start: date
    end: date


class EventCreate(BaseModel):
    """The organizer is the signed-in person. Times are UTC."""
    title: str
    description: str = ""
    start: datetime
    end: datetime
    attendees: list[EventAttendee] = Field(default_factory=list)


class AttendeeAdd(BaseModel):
    personId: str
    optional: bool = False


class ScheduleResult(BaseModel):
    eventId: str
    calendarProvider: str = "demo"
    affected: list["MeetingItem"] = Field(default_factory=list)  # cards created because a key person is out


class ActionRequest(BaseModel):
    action: Action
    proxyId: Optional[str] = None
    note: Optional[str] = None          # optional note to the proxy (only used with action = proxy)
    noteFromAi: bool = False            # the note started as an AI draft (recorded in the history)
    start: Optional[datetime] = None    # reschedule only: a time the organizer picked instead of the proposed one


class NoteDraftAvailable(BaseModel):
    available: bool
    reason: Optional[str] = None   # why not, in plain words, shown under the disabled button


class NoteDraft(BaseModel):
    draft: str
    engine: str = "rules"            # "gemini" | "rules" (AI off) | "rules_fallback" (Gemini failed; simple draft)
    model: Optional[str] = None      # the Gemini model, when engine is "gemini"


class RespondRequest(BaseModel):
    response: ProxyRequestStatus  # accepted | declined


class LeaveSystemRequest(BaseModel):
    personId: str
    start: date
    end: date


class NoActionGroups(BaseModel):
    teamCheckins: list[MeetingItem] = Field(default_factory=list)
    orgEvents: list[MeetingItem] = Field(default_factory=list)
    rescheduledOrCancelled: list[MeetingItem] = Field(default_factory=list)   # the gap is closed: nothing left to do


class AttendeeItems(BaseModel):
    needsAction: list[MeetingItem] = Field(default_factory=list)
    noActionNeeded: NoActionGroups = Field(default_factory=NoActionGroups)


class Counts(BaseModel):
    """attendee / organizer / proxyRequests = number of cards listed in that tab (the number in the brackets).
    attendeeOpen / organizerOpen = how many of them still need the person's action."""
    attendee: int
    organizer: int
    proxyRequests: int
    attendeeOpen: int = 0
    organizerOpen: int = 0
    proxyOpen: int = 0    # proxy requests still waiting for the person's answer


class MeResponse(BaseModel):
    person: Person
    counts: Counts


class ProxyRequestView(BaseModel):
    request: ProxyRequest
    item: MeetingItem
    notesAvailable: bool


class ProxyCandidate(BaseModel):
    personId: str
    rank: int
    reason: str
    choice: Optional[str] = None   # "first" | "second": the recommendation's first and second choice
    declined: bool = False         # already declined to cover this meeting (still pickable by hand)


class ProposedTime(BaseModel):
    proposedStart: Optional[datetime] = None
    windowUsed: Optional[str] = None  # "±1h" | "±2h"
    flagged: bool = False
    none: bool = False


class AbsenceReport(BaseModel):
    """What saving an absence did: shown as a short confirmation ("2 meetings are affected")."""
    absence: "Absence"
    affected: int          # meetings affected (one card each)
    needDecision: int      # of those, how many need a decision


class Metrics(BaseModel):
    """The impact tiles. Formulas and the minutes per action are in config/settings.toml."""
    absencesSpotted: int = 0         # absences in the window
    teamHoursAtRisk: float = 0.0     # estimate: upcoming key meetings without a plan yet
    handledAutomatically: int = 0    # of the meetings with a plan, how many were handled automatically (no person decided)
    meetingsWithPlan: int            # affected meetings that already have a plan
    meetingsAffected: int            # all meetings affected by an absence
    avgNoticeDays: float             # on average, how many days before the meeting the plan was made
    teamHoursSaved: float            # estimated, from the minutes per invitee in [metrics]
    recommendationsFollowedPct: Optional[int] = None   # of the decisions people made, how many followed the recommendation
    decisionsCounted: int = 0        # how many decisions that percentage is based on
    decisionsOnSchedule: int = 0     # key meetings that went ahead (a proxy covered, or without them) instead of waiting
    daysWaitingAvoided: int = 0      # for those: days from the meeting until the absent person was back, added up
    peopleSpared: int = 0            # people in meetings covered, rescheduled or canceled in time (no wasted start)
    estimateNote: str = ""           # how "team time saved" is estimated, in words, built from the config values


class ProjectionRow(BaseModel):
    employees: int
    affectedMeetings: int            # key meetings a year that someone on leave would have missed
    hoursSaved: int                  # team time saved a year (estimate)
    value: int                       # hoursSaved x hourly cost
    decisionsOnSchedule: int         # meetings a year that go ahead instead of waiting
    daysWaitingAvoided: int


class Projection(BaseModel):
    """"At company scale": the measured rates times a company's size. An estimate, labelled as such."""
    rows: list[ProjectionRow]
    measured: bool                   # true = the rates come from the meetings this app handled; false = config fallbacks
    meetingsMeasured: int
    shareClosedEarly: float
    shareWentAhead: float
    peoplePerMeeting: float
    daysWaitingAvoided: float
    leaveDaysPerYear: int
    keyMeetingsPerLeaveDay: float
    minutesSavedPerPerson: int
    hourlyCost: float
    currency: str


OrganizerMeeting.model_rebuild()
MeetingActionRequest.model_rebuild()
AbsenceReport.model_rebuild()
