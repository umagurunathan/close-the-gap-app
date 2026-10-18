"""Who matters in a meeting. Plain rules, shared by the scan, the reschedule search and the agents.

- Optional invitees never matter (they never trigger anything).
- In a normal meeting, the key people are the organizer and the required invitees.
- In a large event (sent to a distribution list, or more than `large_meeting_required_threshold` required invitees),
  ordinary attendees are NOT key people. Only the organizer and people in a hosting role count: named as host,
  organizing committee, speaker, keynote or key guest in the invite or in summaries.
- Distribution lists are never expanded or processed.
"""
from __future__ import annotations

import re
from typing import Optional

from .models import CalEvent, Note, Person
from .settings import settings as S


def required_ids(event: CalEvent) -> list[str]:
    return [a.personId for a in event.attendees if not a.optional]


def is_large_meeting(event: CalEvent) -> bool:
    """Sent to a distribution list, or more required invitees than the threshold in settings."""
    return bool(event.inviteGroup) or len(required_ids(event)) > S.recommendation.large_meeting_required_threshold


def has_hosting_role(event: CalEvent, person: Person, notes: Optional[list[Note]] = None) -> bool:
    """The organizer, or named next to a hosting word in the invite or the summaries the viewer may read."""
    if event.organizerId == person.id:
        return True
    first = person.name.split()[0].lower()
    text = f"{event.title}. {event.description}. " + ". ".join(n.text for n in (notes or []))
    words = S.recommendation.hosting_words
    return any(first in s.lower() and any(w in s.lower() for w in words) for s in re.split(r"(?<=[.!?])\s+", text))


def is_named_in(event: CalEvent, person: Person, notes: Optional[list[Note]] = None) -> bool:
    """The person's name appears in the title, description or the summaries the viewer may read. Used to decide if a
    large event is worth an AI look: "Arjun walks us through the H2 numbers" has no hosting word, but names him."""
    text = f"{event.title} {event.description} " + " ".join(n.text for n in (notes or []))
    first = person.name.split()[0]
    return bool(re.search(rf"\b{re.escape(first)}\b", text, re.IGNORECASE)) or person.name.lower() in text.lower()


def people_count(event: CalEvent) -> int:
    """Everyone in the meeting: the organizer and every invitee (required or optional)."""
    return len({event.organizerId, *(a.personId for a in event.attendees)})


def organizer_is_counterpart(event: CalEvent, absent_id: str) -> bool:
    """In a small meeting the organizer is the other side (e.g. a KT from Priya TO Arjun, organized by Arjun), so they
    cannot stand in for the absent person. `[recommendation] small_meeting_max_people` sets what counts as small."""
    return event.organizerId != absent_id and people_count(event) <= S.recommendation.small_meeting_max_people


def is_one_to_one(event: CalEvent) -> bool:
    """Exactly two people, the organizer included."""
    return people_count(event) == 2


def counterparts(event: CalEvent, absent_id: str) -> set[str]:
    """People on the other side of the meeting from the absent person, who therefore cannot stand in for them.
    In a one-to-one that is the other person, whoever organized it (Priya's 1:1 with Dev: Dev can't cover for Priya).
    In another small meeting it is the organizer, unless the organizer is the one who is out."""
    if is_one_to_one(event):
        return {event.organizerId, *(a.personId for a in event.attendees)} - {absent_id}
    return {event.organizerId} if organizer_is_counterpart(event, absent_id) else set()


def is_invited_as_optional(event: CalEvent, person_id: str) -> bool:
    """Only optional on this invite (not the organizer, not required): such a person never triggers anything."""
    if person_id == event.organizerId:
        return False
    return not any(a.personId == person_id and not a.optional for a in event.attendees)


def key_people(event: CalEvent, people: Optional[dict[str, Person]] = None) -> list[str]:
    """Whose absence needs a decision. In a large event, only the organizer and people in a hosting role
    (`people` is needed to read names; without it, a large event's key person is the organizer alone)."""
    if is_large_meeting(event):
        ids = [event.organizerId]
        if people:
            ids += [pid for pid in required_ids(event) if pid in people and not people[pid].isGroup
                    and has_hosting_role(event, people[pid])]
    else:
        ids = [event.organizerId] + required_ids(event)
    return list(dict.fromkeys(ids))
