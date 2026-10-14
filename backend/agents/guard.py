"""Layer C: plain code that checks every AI answer against our product rules before it reaches a card.

The schema already guarantees the SHAPE of the answer. This file guarantees the RULES that must never be broken,
whatever the model says. Each correction is written into `ai.checks`, so we can see (and later count) what the AI got
wrong.

Rules:
1. A suggested proxy must be one of the candidates (an individual invitee or the organizer, never the absent person or a
   group) and must not be out of office that day. Otherwise the suggestion is dropped and a person must choose.
2. "Proxy" with nobody named means a person must choose.
3. A proxy suggested with no summaries to support it is at most `max_confidence_for_proxy_without_summaries` (it rests
   on the reporting line only). A conclusion from the title or agenda alone is NOT capped.
4. "I'll attend" is never recommended; only the person themselves can choose it. Use the rule-based answer instead.
5. A team check-in needs summaries that show status updates only; without summaries it is a key meeting.
6. A meeting is only auto-handled (team check-in or org-wide event) when confidence is at least `auto_handle_requires`.
7. An org-wide event the absent person organizes or hosts is a key meeting (Decision 48).
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from app.models import Action, AiResult, CalEvent, Confidence, ItemKind, Note, Person
from app.settings import settings as S
from app.roles import has_hosting_role as _has_hosting_role
from .recommender_ai import candidates_for

_RANK = {Confidence.low: 0, Confidence.medium: 1, Confidence.high: 2}


def _at_most(c: Confidence, cap: Confidence) -> Confidence:
    return c if _RANK[c] <= _RANK[cap] else cap


def check(
    kind: ItemKind,
    ai: AiResult,
    event: CalEvent,
    absent: Person,
    people: dict[str, Person],
    notes: list[Note],
    is_out: Callable[[str, date], bool],
    rule_based: Callable[[], tuple[ItemKind, AiResult]],
) -> tuple[ItemKind, AiResult]:
    """`is_out(person_id, day)` says who is on leave; `rule_based()` gives the stand-in's answer for rule 4."""
    fixes: list[str] = []

    # 4. never recommend "attend"
    if ai.recommendation == Action.attend:
        kind, ai = rule_based()
        ai = ai.model_copy()
        ai.engine = "rules_override"   # the card must not say "Gemini": the whole answer now comes from the rules
        fixes.append("the AI recommended 'I'll attend', which only the person can choose; used the rule-based answer")

    # 1. the suggested proxy must be a real, available candidate
    if ai.suggestedProxyId:
        candidate_ids = {c.id for c in candidates_for(event, absent, people)}
        if ai.suggestedProxyId not in candidate_ids:
            fixes.append(f"dropped suggested proxy '{ai.suggestedProxyId}': not one of the candidates")
            ai.suggestedProxyId = None
            ai.reason += " (The suggested person is not invited to this meeting, so please choose a proxy.)"
        elif is_out(ai.suggestedProxyId, event.start.date()):
            dropped = people[ai.suggestedProxyId].name
            fixes.append(f"dropped suggested proxy {dropped}: out of office that day")
            ai.suggestedProxyId = None
            ai.reason += f" (But {dropped} is also out that day, so please choose a proxy.)"

    # 2. a proxy recommendation must name someone, or ask a person to choose
    if ai.recommendation == Action.proxy and not ai.suggestedProxyId and not ai.needsHumanChoice:
        ai.needsHumanChoice = True
        fixes.append("proxy recommended without a person; a person must choose")

    # 3. a proxy chosen with no summaries rests on the reporting line only
    cap = Confidence(S.ai.max_confidence_for_proxy_without_summaries)
    if ai.recommendation == Action.proxy and ai.suggestedProxyId and not notes and _RANK[ai.confidence] > _RANK[cap]:
        fixes.append(f"lowered confidence from {ai.confidence.value} to {cap.value}: proxy chosen with no summaries")
        ai.confidence = _at_most(ai.confidence, cap)

    # 5. a team check-in needs summaries
    if kind == ItemKind.team_checkin and not notes:
        kind = ItemKind.key_meeting
        fixes.append("not marked a team check-in: no summaries confirm it is status updates only")

    # 7. an org-wide event the absent person runs needs a person to look at it
    if kind == ItemKind.org_event and _has_hosting_role(event, absent, notes):
        kind = ItemKind.key_meeting
        fixes.append(f"not marked an org-wide event: {absent.name} organizes or hosts it")

    # 6. auto-handling only when confident enough
    needed = Confidence(S.ai.auto_handle_requires)
    if kind in (ItemKind.team_checkin, ItemKind.org_event) and _RANK[ai.confidence] < _RANK[needed]:
        fixes.append(f"not auto-handled: confidence {ai.confidence.value} is below {needed.value}")
        kind = ItemKind.key_meeting

    ai.checks = [*ai.checks, *fixes]
    return kind, ai
