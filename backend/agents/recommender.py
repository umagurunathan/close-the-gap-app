"""Recommender specialist.

STUB: rule-based so the app runs with no AI key. Replace `recommend` with an ADK/Gemini agent that
returns the same `AiResult` plus an ItemKind. Keep the signature.

What it does:
- Reads only what the viewer may see (summaries shared with them), never more.
- Marks a meeting a "team_checkin" or an "org_event" ONLY when highly confident:
    team_checkin = title says stand-up/status/sync AND visible summaries show status updates only
    org_event    = invite goes to a group / list (town hall, tech talk, social event), AND the absent person
                   is neither its organizer nor named as a host, speaker or committee member
  Recurrence and attendee count are deliberately NOT used.
- Everything else is a "key_meeting": a person decides.
- Otherwise it recommends proxy / reschedule, with an honest confidence and the sources it used.
"""
from __future__ import annotations

import re

from app.models import AiResult, Action, CalEvent, Confidence, ItemKind, Note, Person
from app.settings import settings as S
from .proxy_ranker import rank_proxies

# Word lists and thresholds are tunable in config/settings.toml
ROUTINE_TITLES = tuple(S.recommendation.team_checkin_title_words)
HOSTING_WORDS = tuple(S.recommendation.hosting_words)
DECISION_WORDS = tuple(S.recommendation.decision_words)
MIN_PROXY_SCORE = S.recommendation.min_proxy_score_for_high_confidence


def _has_hosting_role(event: CalEvent, absent: Person, notes: list[Note]) -> bool:
    """The organizer, or named next to a hosting word in the invite or the summaries the viewer may read."""
    if event.organizerId == absent.id:
        return True
    first = absent.name.split()[0].lower()
    text = f"{event.title}. {event.description}. " + ". ".join(n.text for n in notes)
    return any(first in s.lower() and any(w in s.lower() for w in HOSTING_WORDS)
               for s in re.split(r"(?<=[.!?])\s+", text))


def recommend(
    event: CalEvent,
    absent: Person,
    people: dict[str, Person],
    notes: list[Note],
) -> tuple[ItemKind, AiResult]:
    title = event.title.lower()
    fingerprint = [{"docId": n.docId, "modifiedAt": n.modifiedAt.isoformat()} for n in notes]
    text = " ".join(n.text.lower() for n in notes)
    sources = ["invite title", "invite description"]
    if notes:
        sources.insert(0, f"previous summaries ({len(notes)})")
    else:
        sources.append("no summaries available to you")

    # 1) Org-wide events: invite sent to a group/list. Unless the absent person runs it: the organizer, or named as a
    #    host, speaker or committee member. Then they may need to hand it over, so a person must look at it.
    if event.inviteGroup and _has_hosting_role(event, absent, notes):
        ranked = rank_proxies(event, absent, people, notes)
        top = ranked[0] if ranked else None
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy,
            reason=f"{absent.name} organizes or hosts this org-wide event, so someone may need to take over. Please check.",
            confidence=Confidence.medium, sources=["invite organizer", "invite description"] + (["previous summaries"] if notes else []),
            summariesAvailable=bool(notes), suggestedProxyId=top["personId"] if top else None,
            needsHumanChoice=top is None, fingerprint=fingerprint)
    if event.inviteGroup:
        return ItemKind.org_event, AiResult(
            recommendation=Action.proceed_without,
            reason="Org-wide event; one person's absence doesn't affect it. Join if you want the learning.",
            confidence=Confidence.high, sources=["invite goes to a group list", "invite title"],
            summariesAvailable=bool(notes), fingerprint=fingerprint)

    # 2) Routine status meetings: title + summaries showing status updates only
    title_is_routine = any(k in title for k in ROUTINE_TITLES)
    # The stub ignores negations like "no decisions"; a Gemini agent would understand them on its own.
    decision_text = text.replace("no decisions", "").replace("no decision", "")
    has_decisions = any(w in decision_text for w in DECISION_WORDS)
    if title_is_routine and notes and not has_decisions:
        return ItemKind.team_checkin, AiResult(
            recommendation=Action.proceed_without,
            reason="Team check-in; recent summaries show status updates only, no decisions.",
            confidence=Confidence.high, sources=sources, summariesAvailable=True, fingerprint=fingerprint)
    if title_is_routine and not notes:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proceed_without,
            reason="Looks like a team check-in, but no summaries are available to confirm, so please check.",
            confidence=Confidence.medium, sources=sources, summariesAvailable=False)

    # 3) Normal meetings: does the absent person own a decision?
    ranked = rank_proxies(event, absent, people, notes)
    first = absent.name.split()[0].lower()
    owns_decision = bool(notes) and first in text and has_decisions
    top = ranked[0] if ranked else None

    if notes and owns_decision and top and top["score"] >= MIN_PROXY_SCORE:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy,
            reason=f"{absent.name} is named on decisions in the previous summaries; {people[top['personId']].name} is named there too.",
            confidence=Confidence.high, sources=sources, summariesAvailable=True,
            suggestedProxyId=top["personId"], fingerprint=fingerprint)
    if notes and owns_decision:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.reschedule,
            reason=f"{absent.name} owns a decision in this meeting and no one else is clearly able to cover.",
            confidence=Confidence.medium, sources=sources, summariesAvailable=True,
            needsHumanChoice=True, fingerprint=fingerprint)
    if notes:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy if top else Action.reschedule,
            reason="Summaries don't show a decision owned by the absent person.",
            confidence=Confidence.medium, sources=sources, summariesAvailable=True,
            suggestedProxyId=top["personId"] if top else None, needsHumanChoice=top is None,
            fingerprint=fingerprint)

    # 4) No summaries available: fall back to the reporting hierarchy, with lower confidence
    if top and top["score"] > 0:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy,
            reason=f"No summaries available to you. Suggested from the reporting line: {people[top['personId']].name} ({top['reason']}).",
            confidence=Confidence.low, sources=sources, summariesAvailable=False,
            suggestedProxyId=top["personId"])
    return ItemKind.key_meeting, AiResult(
        recommendation=Action.reschedule,
        reason="No summaries available to you and no clear proxy, so a person needs to choose.",
        confidence=Confidence.low, sources=sources, summariesAvailable=False, needsHumanChoice=True)
