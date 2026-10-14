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
    """Organizer Mode card: ONE per meeting, naming everyone who is out (Decision 55). The absent people still each
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
    needsHumanChoice: bool = False
    fingerprint: list[dict] = Field(default_factory=list)
    # Who produced this answer: "gemini" (possibly adjusted by the checks; see `checks`), "rules" (AI switched off),
    # "rules_fallback" (the AI was unavailable) or "rules_override" (the checks rejected the AI's whole answer).
    # The card shows a green tag for Gemini and a grey one for the rules.
    engine: str = "rules"
    model: Optional[str] = None   # the Gemini model that produced the answer (engine "gemini")
    # Corrections the checking layer (agents/guard.py) made to the AI's answer, in plain words. Empty = none needed.
    checks: list[str] = Field(default_factory=list)


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
    # Computed when listing (not stored); the same for every viewer:
    needsAttention: bool = False          # still needs someone to act (not settled)
    urgency: Optional[str] = None         # "soon" (<= 3 days) | "urgent" (<= 24 hours), only while needsAttention
    hoursToStart: Optional[float] = None  # hours until the meeting starts, while needsAttention
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
    detail: str
    at: datetime


# ---- Simulated calendar (stands in for Google Calendar + shared notes) ----

class Note(BaseModel):
    """A meeting summary / notes doc. Only readable by people it is shared with (and the organizer)."""
    docId: str
    modifiedAt: datetime
    text: str
    sharedWith: list[str] = Field(default_factory=list)


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
    affected: list["MeetingItem"] = Field(default_factory=list)  # cards created because a key person is out


class ActionRequest(BaseModel):
    action: Action
    proxyId: Optional[str] = None
    note: Optional[str] = None          # optional note to the proxy (only used with action = proxy)
    noteFromAi: bool = False            # the note started as an AI draft (recorded in the history)


class NoteDraftAvailable(BaseModel):
    available: bool


class NoteDraft(BaseModel):
    draft: str


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


class ProposedTime(BaseModel):
    proposedStart: Optional[datetime] = None
    windowUsed: Optional[str] = None  # "±1h" | "±2h"
    flagged: bool = False
    none: bool = False


class Metrics(BaseModel):
    meetingsResolved: int
    avgLeadTimeDays: float
    attendeeMinutesSaved: int


OrganizerMeeting.model_rebuild()
MeetingActionRequest.model_rebuild()
