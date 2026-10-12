"""Orchestrator: takes one affected meeting, calls the specialists, returns the card's AI block.

STUB: calls the two rule-based specialists. With ADK this becomes a root agent that calls the recommender
and proxy-ranker agents as tools. Keep `analyze` as the one entry point the backend calls.
"""
from __future__ import annotations

from app.calendar import SimCalendar
from app.models import AiResult, CalEvent, ItemKind, Person
from .recommender import recommend


def analyze(
    event: CalEvent,
    absent: Person,
    viewer_id: str,
    people: dict[str, Person],
    calendar: SimCalendar,
) -> tuple[ItemKind, AiResult]:
    """`viewer_id` = the person who will decide (leaver or organizer). Only summaries they can open are read."""
    notes = calendar.visible_notes(event, viewer_id)
    return recommend(event, absent, people, notes)
