"""Orchestrator: takes one affected meeting, calls the specialists, returns the card's AI block.

With `[ai] enabled = false` (config/settings.toml) the rule-based stand-ins decide. With `true`:
  1. with `[ai] engine = "adk"`, the meeting advisor agent decides using its tools (agents/adk_advisor.py), once;
  2. otherwise, or if the agent fails, one Gemini call with everything in the prompt (agents/recommender_ai.py);
     temporary failures (too many requests, server errors, timeouts) are retried a few times with short waits,
  3. whichever answered, the answer is checked against our rules by plain code (agents/guard.py, layer C),
  4. if the AI is still unavailable, the rule-based answer is used and labelled "AI unavailable" on the card.
The AI can therefore never block or break the app. Keep `analyze` as the one entry point the backend calls.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Callable, Optional

from app.calendar import SimCalendar
from app.models import AiResult, CalEvent, ItemKind, Person
from app.roles import has_hosting_role, is_large_meeting, is_named_in
from app.settings import settings as S
from .recommender import recommend

log = logging.getLogger("close_the_gap.ai")


def _is_temporary(err: Exception) -> bool:
    """Worth retrying: too many requests (429), Google-side errors (5xx), timeouts and lost connections.
    Not worth retrying: our own mistakes (other 4xx), which would fail the same way again."""
    code = getattr(err, "code", None)
    if isinstance(code, int):
        return code in S.ai.retry_status_codes or code >= 500
    return True   # timeouts and connection errors carry no status code


def _with_retries(call: Callable[[], tuple[ItemKind, AiResult]]) -> tuple[ItemKind, AiResult]:
    waits = list(S.ai.retry_wait_seconds)
    for attempt in range(1, S.ai.attempts + 1):
        try:
            return call()
        except Exception as err:   # noqa: BLE001 - any failure here must fall back, never reach the user
            if attempt == S.ai.attempts or not _is_temporary(err):
                raise
            wait = waits[min(attempt - 1, len(waits) - 1)] if waits else 0
            log.warning("AI attempt %s failed (%s); retrying in %ss", attempt, type(err).__name__, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def ai_needed(event: CalEvent, absent: Person, notes) -> bool:
    """False when our rules answer on their own, with no AI review: a large event where this person has no hosting
    role (Decision 55) and is not even named in it. If they are named ("Arjun walks us through the H2 numbers"), the
    AI looks (`[ai] large_event_ai_when_named`), because a keyword list cannot catch every way of saying "presents".
    Large events stay cheap: one AI call only for people the event actually mentions, never for the whole audience."""
    if not is_large_meeting(event) or has_hosting_role(event, absent, notes):
        return True
    return bool(S.ai.large_event_ai_when_named) and is_named_in(event, absent, notes)


def analyze(
    event: CalEvent,
    absent: Person,
    viewer_id: str,
    people: dict[str, Person],
    calendar: SimCalendar,
    is_out: Optional[Callable[[str, date], bool]] = None,
    use_ai: bool = True,
) -> tuple[ItemKind, AiResult]:
    """`viewer_id` = the person who will decide (leaver or organizer). Only summaries they can open are read.
    `is_out(person_id, day)` tells the checks who is on leave. `use_ai=False` gives the rule-based answer even when the
    AI is on (used while creating cards, so nothing waits for the AI)."""
    notes = calendar.visible_notes(event, viewer_id)
    rule_based = lambda: recommend(event, absent, people, notes)   # noqa: E731
    if not (S.ai.enabled and use_ai):
        return rule_based()

    # A large event where this person has no hosting role needs no AI review (Decision 55): plain rules, no cost.
    if not ai_needed(event, absent, notes):
        kind, ai = rule_based()
        ai.engine = "rules_policy"
        ai.checks = ["large event, no hosting role and not named in it: handled by our rules, no AI review needed"]
        return kind, ai

    from . import guard
    from . import recommender_ai   # imported here so the app runs without the Google library when AI is off
    check = lambda k, a: guard.check(k, a, event, absent, people, notes, is_out or (lambda _p, _d: False), rule_based)  # noqa: E731

    # 1. The ADK agent, once (it already makes several calls; a failure goes straight to the single call below).
    agent_note = None
    if S.ai.engine == "adk":
        from . import adk_advisor
        try:
            kind, ai = adk_advisor.recommend_adk(event, absent, people, notes, is_out=is_out)
            ai.engine = "gemini_adk"
            return check(kind, ai)
        except Exception as err:   # noqa: BLE001
            log.warning("ADK agent failed for '%s' (%s): using the single Gemini call", event.title, err)
            agent_note = f"ADK agent unavailable ({type(err).__name__}); answered by a single Gemini call"

    # 2. One Gemini call with everything in the prompt, retried on temporary errors.
    try:
        kind, ai = _with_retries(lambda: recommender_ai.recommend_ai(event, absent, people, notes, is_out=is_out))
    except Exception as err:   # noqa: BLE001
        # 3. The rules, labelled on the card.
        log.warning("AI unavailable for '%s' (%s): using the rule-based answer", event.title, err)
        if not S.ai.fall_back_to_rules:
            raise
        kind, ai = rule_based()
        ai.engine = "rules_fallback"
        ai.checks = [f"AI unavailable ({type(err).__name__}); rule-based suggestion shown"]
        return kind, ai

    ai.engine = "gemini"
    ai.checks = [agent_note] if agent_note else []
    return check(kind, ai)
