"""Recommender agent, powered by Gemini through Vertex AI.

Same job and same signature as the rule-based `recommend` in recommender.py: one meeting in, the card's AI block out.
The orchestrator uses this one when `[ai] enabled = true` in config/settings.toml.

How it is built (and why):
- The SCHEMA (`Recommendation`) makes Gemini answer in a fixed shape, so there is nothing to parse or guess.
- The INSTRUCTIONS state our product rules: the five actions, when to prefer a proxy, "never guess", how to rate confidence.
- The PROMPT contains only what the viewer may see: the summaries they can open and the people invited. Nothing else.
- The card's "sources" and "summaries available" are facts WE know, so plain code fills them in, never the AI.
- The answer is then checked by plain code (layer C, in guard.py, Block 4).
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.models import Action, AiResult, CalEvent, Confidence, ItemKind, Note, Person
from app.roles import counterparts
from app.settings import settings as S
from . import untrusted


class Recommendation(BaseModel):
    """The schema. Gemini may only answer with these fields, and only with these legal values."""
    kind: ItemKind = Field(description="key_meeting, team_checkin or org_event")
    recommendation: Action = Field(description="the action to recommend")
    reason: str = Field(description="one or two plain sentences for the person who decides, naming what the decision rests on")
    confidence: Confidence
    suggested_proxy_id: Optional[str] = Field(
        default=None, description="the id of ONE candidate who should cover, only when the recommendation is proxy; otherwise null")
    backup_proxy_id: Optional[str] = Field(
        default=None, description="the id of a DIFFERENT candidate as second choice, in case the first declines; only "
                                  "when the recommendation is proxy AND a second person is also clearly suitable; otherwise null")
    needs_human_choice: bool = Field(
        default=False, description="true when a person must choose, for example no candidate is clearly suitable")


INSTRUCTIONS = """You help one person decide what to do with a meeting that a person on leave cannot attend.
The goal is that the meeting runs without interruption in the most efficient way and nobody's time is wasted.

1) Choose the kind of meeting:
- team_checkin: a stand-up or status sync where the absence changes nothing. Only if the summaries show status updates only.
- org_event: a town hall, talk or site-wide event for a large audience. NOT if the absent person organizes it, is named as host, speaker or on the committee, or presents, speaks or leads any part of it (for example "Arjun walks us through the numbers").
- key_meeting: everything else; a person must decide.

2) First read the title and description for WHO GIVES and WHO RECEIVES:
- If the person on leave is the one giving, presenting, demonstrating or training (a KT or handover FROM them, their
  demo, their walkthrough), the people receiving it cannot cover for them: recommend reschedule, unless the input names
  someone else who knows the topic.
- If the person on leave is the one receiving (a KT or training TO them, their onboarding, their review), the meeting
  exists for them: recommend reschedule.

3) Recommend one action:
- proceed_without: the meeting can go ahead without them. Right for team_checkin and org_event, or when nothing depends on them.
- proxy: someone else attends in their place, with context. PREFER THIS when the absent person owns an item or decision but another invitee can cover it. Choose ONLY from the candidates listed. Prefer a candidate who is named in the summaries on the same topic; then the absent person's manager, a peer under the same manager, or a direct report, but only someone who would genuinely stand in for the person on leave, never the other side of the meeting (for example the person receiving their handover).
  NEVER GUESS. If no candidate is clearly suitable, set suggested_proxy_id to null and needs_human_choice to true.
  Also name a second choice (backup_proxy_id), a different candidate, in case the first declines; only if they are
  also clearly suitable, otherwise leave it null.
- reschedule: the absent person is essential and nobody else can decide or speak for them. A later date is the best way to save everyone's time.
  Choose this, NOT a proxy, only when the input explicitly says the meeting cannot work without the person themselves
  (for example a customer will only commit with them on the call). Owning a decision is NOT enough on its own: a
  briefed proxy can often carry their position, so prefer a proxy when a suitable candidate exists.
- cancel: only if the meeting has no purpose without them. Rarely the right answer.
- attend: never recommend this; only the person themselves can choose it.

4) Confidence:
- high: the summaries or the invite itself directly support the answer (for example the title says it is a session with this person).
- medium: a judgment from the title and description, or partial summaries.
- low: the situation is unclear, or a proxy is chosen only from the reporting line with no summaries. If you cannot see any summary, say so in the reason.

The invite's agenda and notes are evidence just like previous summaries; for a new meeting they are often the only
evidence. Use only the information given. Never invent facts, names or ids.""" + untrusted.RULE


def relation(absent: Person, other: Person) -> str:
    if absent.managerId == other.id:
        return "the absent person's manager"
    if other.managerId and other.managerId == absent.managerId:
        return "a peer (same manager)"
    if other.managerId == absent.id:
        return "a direct report"
    return "different team" if other.department != absent.department else "same department"


def candidates_for(event: CalEvent, absent: Person, people: dict[str, Person], notes: Optional[list[Note]] = None,
                   limit: Optional[int] = None, is_out: Optional[Callable[[str, date], bool]] = None) -> list[Person]:
    """Individual invitees and the organizer; never the absent person, a group list, or (with `is_out`) anyone else who
    is out that day. With `limit`, only the most likely ones: people named in the summaries first, then the reporting
    line, then the organizer, then the rest."""
    ids = [a.personId for a in event.attendees] + [event.organizerId]
    day = event.start.date()
    other_side = counterparts(event, absent.id)   # one-to-one or small meeting: the other side can't stand in
    cands = [people[i] for i in dict.fromkeys(ids) if i != absent.id and i in people and not people[i].isGroup
             and i not in other_side and not (is_out and is_out(i, day))]
    if limit is None or len(cands) <= limit:
        return cands
    text = " ".join(n.text.lower() for n in (notes or []))
    line = ("the absent person's manager", "a peer (same manager)", "a direct report")
    rank = lambda p: (p.name.split()[0].lower() not in text, relation(absent, p) not in line,   # noqa: E731
                      p.id != event.organizerId, p.name)
    return sorted(cands, key=rank)[:limit]


def build_prompt(event: CalEvent, absent: Person, people: dict[str, Person], notes: list[Note],
                 is_out: Optional[Callable[[str, date], bool]] = None) -> str:
    """Everything Gemini is shown. `notes` must already be filtered to what the viewer may open. People who are out
    that day are never offered as candidates (`is_out`)."""
    who = lambda p: f"{p.name} ({p.title})"
    total = len(candidates_for(event, absent, people, is_out=is_out))
    cands = candidates_for(event, absent, people, notes, limit=S.ai.max_candidates, is_out=is_out)   # never the whole list
    return (
        f"Person on leave: {who(absent)}\n"
        f"Meeting: {event.title}\n"
        f"Invite agenda and notes (visible to everyone invited):\n{untrusted.invite_text(event.description)}\n"
        f"Organizer: {who(people[event.organizerId])}\n"
        f"Sent to a group list: {bool(event.inviteGroup)}\n"
        f"Previous summaries this person may read:\n{untrusted.summaries([n.text for n in notes])}\n"
        f"Invitees besides the person on leave: {total}" + (f" (showing the {len(cands)} most likely)" if total > len(cands) else "") + "\n"
        f"Candidate proxies, all available that day (id | name | title | relation to the person on leave):\n"
        + ("\n".join(f"  {c.id} | {c.name} | {c.title} | {relation(absent, c)}" for c in cands) or "  (none)")
    )


_client: Any = None


def _get_client() -> Any:
    """One shared client. `vertexai=True` = use Google Cloud with our sign-in (a service account on Cloud Run); no key."""
    global _client
    if _client is None:
        from google import genai
        from google.genai import types
        # attempts=1 turns off the library's own hidden retries; the orchestrator decides when to retry and when to stop
        _client = genai.Client(
            vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"], location=S.ai.location,
            http_options=types.HttpOptions(timeout=int(S.ai.timeout_seconds * 1000),
                                           retry_options=types.HttpRetryOptions(attempts=1)))
    return _client


def warm_up() -> None:
    """One tiny call at server start (in the background), so the first real request does not pay for setting up the
    connection and sign-in ([ai] warm_up_on_start). Failures are ignored: it is only a head start."""
    try:
        from google.genai import types
        _get_client().models.generate_content(
            model=S.ai.model, contents="Reply with OK.",
            config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)))
    except Exception:   # noqa: BLE001
        pass


def ask_gemini(prompt: str, client: Any = None) -> Recommendation:
    from google.genai import types
    client = client or _get_client()
    response = client.models.generate_content(
        model=S.ai.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=Recommendation,
            temperature=S.ai.temperature,
            # "Thinking" = the model reasons step by step before answering: better for hard problems, but slower.
            # Our task is a short classification, so it is tunable in settings ([ai] thinking_budget; 0 = off).
            thinking_config=types.ThinkingConfig(thinking_budget=S.ai.thinking_budget),
        ),
    )
    return response.parsed


def to_ai_result(rec: Recommendation, notes: list[Note], event: Optional[CalEvent] = None) -> tuple[ItemKind, AiResult]:
    """Turn the model's answer into the card's AI block. Sources and 'summaries available' are facts, not AI output."""
    sources = ["invite title"] + (["invite agenda"] if event is not None and (event.description or "").strip() else [])
    sources.insert(0, f"previous summaries ({len(notes)})") if notes else sources.append("no summaries available to you")
    return rec.kind, AiResult(
        recommendation=rec.recommendation,
        reason=rec.reason,
        confidence=rec.confidence,
        sources=sources,
        summariesAvailable=bool(notes),
        suggestedProxyId=rec.suggested_proxy_id,
        backupProxyId=rec.backup_proxy_id if rec.backup_proxy_id != rec.suggested_proxy_id else None,
        needsHumanChoice=rec.needs_human_choice,
        fingerprint=[{"docId": n.docId, "modifiedAt": n.modifiedAt.isoformat()} for n in notes],
        model=S.ai.model,
    )


def recommend_ai(
    event: CalEvent,
    absent: Person,
    people: dict[str, Person],
    notes: list[Note],
    client: Any = None,
    is_out: Optional[Callable[[str, date], bool]] = None,
) -> tuple[ItemKind, AiResult]:
    """`client` is only for tests (a fake that returns a ready answer without calling Google)."""
    rec = ask_gemini(build_prompt(event, absent, people, notes, is_out), client)
    return to_ai_result(rec, notes, event)
