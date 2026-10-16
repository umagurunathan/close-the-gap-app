"""Draft a handover note for a proxy: a short, contextual brief written by Gemini.

The note goes out WITH the proxy request, before the proxy has agreed, so it asks ("could you cover…?") and tells the
proxy what they would be covering.

How it works (`draft_note`, the entry point, below):
1. Gemini writes the brief: one call with a fixed answer shape (`HandoverBrief`): what the meeting is for, what the
   proxy would cover, key points and open items from earlier summaries, who to check with. One call and not an agent:
   nothing needs looking up, the facts are already chosen and filtered for privacy by the caller.
2. Our code writes the greeting and the layout (`render`), so the AI cannot change who the note is for or add a
   signature, and plain-code checks trim and cap the points and fix "check with" (`_check_with`).
3. Only if the AI is switched off or Gemini fails: the simple rule-based draft in agents/fallback/simple_note.py,
   and the panel says "Simple draft · AI unavailable".
The sender always reads and edits the draft before sending.

Privacy rule (enforced by the caller, Service._draft_notes): `notes` holds ONLY summaries that both the
sender and the chosen proxy can open, so the brief cannot reveal anything the proxy may not read.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models import CalEvent, Note, Person
from app.settings import settings as S
from . import untrusted
from .fallback.simple_note import draft_note_rules   # FALLBACK ONLY: AI off, or Gemini failed

log = logging.getLogger("close_the_gap.ai")


# ================================================================ entry point
def draft_note(event: CalEvent, absent: Person, notes: list[Note], proxy: Optional[Person] = None,
               client: Any = None, organizer: Optional[Person] = None) -> tuple[str, str]:
    """Returns (text, engine): engine "gemini", "rules" (AI off) or "rules_fallback" (Gemini failed).
    `client` is only for tests (a fake that returns a ready answer without calling Google)."""
    if not S.ai.enabled:
        return draft_note_rules(event, absent, notes, proxy, organizer), "rules"
    from .orchestrator import _with_retries
    try:
        brief = _with_retries(lambda: ask_gemini(build_prompt(event, absent, notes, proxy, organizer), client))
        return render(brief, event, absent, proxy, organizer), "gemini"
    except Exception as err:   # noqa: BLE001 - the sender must always get a draft
        log.warning("AI note draft failed for '%s' (%s): using the simple draft", event.title, err)
        return draft_note_rules(event, absent, notes, proxy, organizer), "rules_fallback"


# ================================================================ 1. the Gemini brief
class HandoverBrief(BaseModel):
    """The schema. Short fields; our code turns them into the note."""
    meeting_purpose: str = Field(description="one sentence: what this meeting is for, from the title, description and summaries")
    covering_for: str = Field(
        description="one or two sentences addressed to the proxy as 'you', e.g. 'You would represent Priya, who owns the "
                    "final vendor decision and sign-off.' Name a responsibility ONLY if the input states it; otherwise "
                    "just say 'You would attend in Priya's place.'")
    key_points: list[str] = Field(
        description="up to 5 short facts from the summaries the proxy needs: decisions taken, who owns what")
    open_items: list[str] = Field(
        description="up to 4 short items still pending: decisions to take, things to confirm or prepare. Empty if none")
    check_with: str = Field(
        description="one sentence: who to check with (by name, only people mentioned in the input) if something is unclear")


INSTRUCTIONS = """You write a short handover brief for a colleague (the proxy) who is being asked to attend a meeting in
place of someone who is on leave. They have not agreed yet: the brief helps them decide and, if they accept, walk into
the meeting knowing what it is for, what they would cover, what was already decided and what is still open.

Rules:
- Use ONLY the meeting details and the previous summaries given. Never invent decisions, numbers, dates or names.
- If the summaries do not say something, leave it out rather than guess.
- Plain, friendly, professional English. Short sentences. No greeting and no signature (they are added separately).
- The note is addressed to the proxy: ALWAYS call the proxy "you", never by their name. If a summary names the proxy,
  write "you" (for example "You own the final mockups").
- They have not agreed yet: write "you would…", not "you are covering". Never attribute a responsibility, decision or
  sign-off to anyone unless the input states it; if it does not say what the person on leave owns, just say the proxy
  would attend in their place.
- The person on leave is away during this meeting: never tell the proxy to check with them or wait for them.
- Write open items as what the proxy may need to raise, decide or confirm in the meeting on the absent person's behalf.
- For "check_with", suggest the organizer (or another person named in the input), never the proxy or the person on leave.
- Refer to other people by first name.""" + untrusted.RULE


def build_prompt(event: CalEvent, absent: Person, notes: list[Note], proxy: Optional[Person],
                 organizer: Optional[Person] = None) -> str:
    """Everything Gemini is shown. `notes` must already be the summaries both the sender and the proxy may open.
    An agenda that tries to instruct the AI is left out altogether (plain code, not the model's judgment)."""
    agenda = ("(left out: it contained instructions aimed at the AI)" if untrusted.looks_like_injection(event.description)
              else event.description)
    return (
        f"Meeting: {event.title}\n"
        f"Date: {event.start.date().isoformat()}\n"
        f"Invite agenda and notes:\n{untrusted.invite_text(agenda)}\n"
        f"Organizer: " + (f"{organizer.name} ({organizer.title})" if organizer else "(unknown)") + "\n"
        f"Person on leave: {absent.name} ({absent.title})\n"
        f"Proxy: " + (f"{proxy.name} ({proxy.title})" if proxy else "(not named)") + "\n"
        f"Previous summaries:\n{untrusted.summaries([n.text for n in notes], empty='(none)')}"
    )


def ask_gemini(prompt: str, client: Any = None) -> HandoverBrief:
    from google.genai import types

    from .recommender_ai import _get_client
    client = client or _get_client()
    response = client.models.generate_content(
        model=S.ai.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=HandoverBrief,
            temperature=S.drafter.temperature,   # a little variety in wording; the facts come from the summaries
            thinking_config=types.ThinkingConfig(thinking_budget=S.ai.thinking_budget),
        ),
    )
    return response.parsed


# ================================================================ 2. our code: greeting, layout and checks
def _greeting(event: CalEvent, absent: Person, proxy: Optional[Person]) -> str:
    """The note asks: it goes out with the request, before the proxy has agreed."""
    hello = f"Hi {proxy.name.split()[0]}," if proxy else "Hi,"
    return (f"{hello} could you cover '{event.title}' on {event.start.strftime('%a %d %b')} for "
            f"{absent.name.split()[0]}? Here's what you need to know:")


def _check_with(text: str, absent: Person, proxy: Optional[Person], organizer: Optional[Person]) -> str:
    """Plain-code check: never send the proxy to themselves or to the person who is away."""
    text = text.strip()
    bad = {absent.name.split()[0].lower()} | ({proxy.name.split()[0].lower()} if proxy else set())
    if text and not any(re.search(rf"\b{re.escape(b)}\b", text.lower()) for b in bad):
        return text
    return _ask_organizer(absent, proxy, organizer)


def _ask_organizer(absent: Person, proxy: Optional[Person], organizer: Optional[Person]) -> str:
    if organizer and organizer.id != absent.id and (not proxy or organizer.id != proxy.id):
        return f"If anything is unclear, check with {organizer.name.split()[0]}, who organizes the meeting."
    return "If anything is unclear, reply to this note."


def render(brief: HandoverBrief, event: CalEvent, absent: Person, proxy: Optional[Person],
           organizer: Optional[Person] = None) -> str:
    """Our code writes the greeting and layout; the AI only fills the content. Plain-code checks happen here."""
    clean = lambda items, cap: [s.strip() for s in items if s and s.strip()][:cap]   # noqa: E731
    points = clean(brief.key_points, S.drafter.max_key_points)
    open_items = clean(brief.open_items, S.drafter.max_open_items)
    parts = [_greeting(event, absent, proxy), "", brief.meeting_purpose.strip(), brief.covering_for.strip()]
    if points:
        parts += ["", "Key points from earlier meetings:"] + [f"- {p}" for p in points]
    if open_items:
        parts += ["", "Still open:"] + [f"- {p}" for p in open_items]
    parts += ["", _check_with(brief.check_with, absent, proxy, organizer)]
    return "\n".join(p for p in parts if p is not None).strip()
