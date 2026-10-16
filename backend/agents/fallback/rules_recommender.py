"""FALLBACK ONLY: the rule-based recommender, used when the AI is off or Gemini is unavailable.

The product's recommendation comes from Gemini (agents/adk_advisor.py, agents/recommender_ai.py). These keyword rules
keep the app working without it, give each card a first answer while the AI works, and are shown on the card as
"what simple rules would have said" when the AI's answer differs. Same signature and result as the AI recommender.

What the rules do:
- Read only what the viewer may see (summaries shared with them), never more.
- Mark a meeting a "team_checkin" or an "org_event" ONLY when confident:
    team_checkin = title says stand-up/status/sync AND visible summaries show status updates only
    org_event    = a large event (sent to a list, or more required invitees than the threshold in settings),
                   AND the absent person is neither its organizer nor in a hosting role (host, committee, speaker,
                   keynote or key guest).
  Recurrence is deliberately NOT used. Attendee count is used only to recognise a large event.
- Everything else is a "key_meeting": a person decides; proxy / reschedule with an honest confidence and sources.
They cannot read meaning: "no decisions" vs "decision", a "sync" that is really a sign-off, a customer who insists on
one person, a handover FROM vs TO someone. That is what the AI is for.
"""
from __future__ import annotations

import logging

from app import config
from app.models import AiResult, Action, CalEvent, Confidence, ItemKind, Note, Person
from app.roles import has_hosting_role, is_large_meeting, organizer_is_counterpart
from app.settings import settings as S
from .candidate_order import rank_proxies
from ..vertex_proxy_ranker import suggest_proxy

logger = logging.getLogger(__name__)

# Word lists and thresholds are tunable in config/settings.toml
ROUTINE_TITLES = tuple(S.recommendation.team_checkin_title_words)
HOSTING_WORDS = tuple(S.recommendation.hosting_words)
DECISION_WORDS = tuple(S.recommendation.decision_words)
MIN_PROXY_SCORE = S.recommendation.min_proxy_score_for_high_confidence


def _has_hosting_role(event: CalEvent, absent: Person, notes: list[Note]) -> bool:
    return has_hosting_role(event, absent, notes)   # the shared rule lives in app/roles.py


def recommend(
    event: CalEvent,
    absent: Person,
    people: dict[str, Person],
    notes: list[Note],
) -> tuple[ItemKind, AiResult]:
    title = event.title.lower()
    fingerprint = [{"docId": n.docId, "modifiedAt": n.modifiedAt.isoformat()} for n in notes]
    text = " ".join(n.text.lower() for n in notes)
    sources = ["invite title"] + (["invite agenda"] if (event.description or "").strip() else [])
    if notes:
        sources.insert(0, f"previous summaries ({len(notes)})")
    else:
        sources.append("no summaries available to you")

    # 1) Org-wide or large events. Unless the absent person runs it (organizer, host, committee, speaker, keynote or
    #    key guest): then they may need to hand it over, so a person must look at it.
    large = is_large_meeting(event)
    if large and _has_hosting_role(event, absent, notes):
        ranked = rank_proxies(event, absent, people, notes)
        top = ranked[0] if ranked else None
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy,
            reason=f"{absent.name} organizes or hosts this org-wide event, so someone may need to take over. Please check.",
            confidence=Confidence.medium, sources=["invite organizer", "invite agenda"] + (["previous summaries"] if notes else []),
            summariesAvailable=bool(notes), suggestedProxyId=top["personId"] if top else None,
            needsHumanChoice=top is None, fingerprint=fingerprint)
    if large:
        return ItemKind.org_event, AiResult(
            recommendation=Action.proceed_without,
            reason="Org-wide event; one person's absence doesn't affect it. Join if you'd like to.",
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
    if organizer_is_counterpart(event, absent.id):   # small meeting: the organizer is the other side, never suggested
        ranked = [r for r in ranked if r["personId"] != event.organizerId]
    # second choice for a proxy recommendation: the next-ranked person, only if they have some supporting link
    backup = ranked[1]["personId"] if len(ranked) > 1 and ranked[1]["score"] > 0 else None
    if notes and ranked and config.llm_provider() == "vertex":
        try:
            suggestion = suggest_proxy(event, absent, people, notes, ranked)
        except Exception:
            logger.warning("Vertex proxy suggestion failed; using the rule-based ranking", exc_info=True)
            suggestion = None
        if suggestion:
            return ItemKind.key_meeting, AiResult(
                recommendation=Action.proxy,
                reason=f"{suggestion.reason} Evidence: \"{suggestion.evidence_quote}\"",
                confidence=Confidence(suggestion.confidence), sources=sources + ["Vertex AI Gemini"],
                summariesAvailable=True, suggestedProxyId=suggestion.person_id,
                needsHumanChoice=suggestion.confidence == "low", fingerprint=fingerprint)

    first = absent.name.split()[0].lower()
    owns_decision = bool(notes) and first in text and has_decisions
    top = ranked[0] if ranked else None

    if notes and owns_decision and top and top["score"] >= MIN_PROXY_SCORE:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy,
            reason=f"{absent.name} is named on decisions in the previous summaries; {people[top['personId']].name} is named there too.",
            confidence=Confidence.high, sources=sources, summariesAvailable=True,
            suggestedProxyId=top["personId"], backupProxyId=backup, fingerprint=fingerprint)
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
            suggestedProxyId=top["personId"] if top else None, backupProxyId=backup if top else None,
            needsHumanChoice=top is None,
            fingerprint=fingerprint)

    # 4) No summaries available: fall back to the reporting hierarchy, with lower confidence
    if top and top["score"] > 0:
        return ItemKind.key_meeting, AiResult(
            recommendation=Action.proxy,
            reason=f"No summaries available to you. Suggested from the reporting line: {people[top['personId']].name} ({top['reason']}).",
            confidence=Confidence.low, sources=sources, summariesAvailable=False,
            suggestedProxyId=top["personId"], backupProxyId=backup)
    return ItemKind.key_meeting, AiResult(
        recommendation=Action.reschedule,
        reason="No summaries available to you and no clear proxy, so a person needs to choose.",
        confidence=Confidence.low, sources=sources, summariesAvailable=False, needsHumanChoice=True)
