"""Who matters in a meeting. Plain rules, shared by the scan, the reschedule search and the agents.

- Optional invitees never matter (they never trigger anything).
- In a normal meeting, the key people are the organizer and the required invitees.
- In a large event (sent to a distribution list, or more than `large_meeting_required_threshold` required invitees),
  ordinary attendees are NOT key people. Only the organizer and people in a hosting role count: named as host,
  organizing committee, speaker, keynote or key guest in the invite or in summaries (Decisions 48 and 55).
- Distribution lists are never expanded or processed (Decision 55).
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
