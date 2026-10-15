"""Draft a handover note for a proxy: a short, contextual brief from the meeting and its previous summaries.

With `[ai] enabled = true` Gemini writes it (one call, structured output). Why one call and not an agent: nothing needs
looking up. The facts are already chosen and already filtered for privacy by the caller.

Privacy rule (enforced by the caller, Service._draft_notes, Decision 57): `notes` holds ONLY summaries that both the
sender and the chosen proxy can open, so the brief cannot reveal anything the proxy may not read.

Safety net, same pattern as the recommender:
- a fixed answer shape (`HandoverBrief`); OUR code writes the greeting and layout, so the AI cannot change who the note
  is for or add a signature;
- instructions: use only the summaries given, never invent decisions, numbers or names;
- plain-code checks: trim, drop empty points, cap the number of points;
- if Gemini fails or the AI is off, the simple rule-based draft is used and the panel says so;
- the sender always reads and edits the draft before sending.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models import CalEvent, Note, Person
from app.settings import settings as S

log = logging.getLogger("close_the_gap.ai")
KEY_WORDS = tuple(S.drafter.key_words)   # tunable in config/settings.toml


# ---------------------------------------------------------------- the simple draft (no AI; also the fallback)
def draft_note_rules(event: CalEvent, absent: Person, notes: list[Note]) -> str:
    first = absent.name.split()[0]
    sentences: list[str] = []
    for n in notes:
        for s in re.split(r"(?<=[.!?])\s+", n.text.strip()):
            low = s.lower()
            if s and (first.lower() in low or any(k in low for k in KEY_WORDS)) and s not in sentences:
                sentences.append(s)
    if not sentences and notes:
        sentences = re.split(r"(?<=[.!?])\s+", notes[0].text.strip())[:S.drafter.fallback_sentences]
    bullets = "\n".join(f"- {s}" for s in sentences[:S.drafter.max_bullets])
    return (
        f"Hi, thanks for covering '{event.title}' for {first}.\n"
        f"From the previous summaries:\n{bullets}\n"
        f"Please check with {first} if anything is unclear."
    )


# ---------------------------------------------------------------- the Gemini brief
class HandoverBrief(BaseModel):
    """The schema. Short fields; our code turns them into the note."""
    meeting_purpose: str = Field(description="one sentence: what this meeting is for, from the title, description and summaries")
    covering_for: str = Field(
        description="one or two sentences addressed to the proxy as 'you': what the person on leave owns, decides or "
                    "presents in this meeting, which the proxy now covers. Only what the summaries or invite support")
    key_points: list[str] = Field(
        description="up to 5 short facts from the summaries the proxy needs: decisions taken, who owns what")
    open_items: list[str] = Field(
        description="up to 4 short items still pending: decisions to take, things to confirm or prepare. Empty if none")
    check_with: str = Field(
        description="one sentence: who to check with (by name, only people mentioned in the input) if something is unclear")


INSTRUCTIONS = """You write a short handover brief for a colleague (the proxy) who will attend a meeting in place of
someone who is on leave. The proxy must walk into the meeting knowing what it is for, what they are covering, what was
already decided and what is still open.

Rules:
- Use ONLY the meeting details and the previous summaries given. Never invent decisions, numbers, dates or names.
- If the summaries do not say something, leave it out rather than guess.
- Plain, friendly, professional English. Short sentences. No greeting and no signature (they are added separately).
- The note is addressed to the proxy: ALWAYS call the proxy "you", never by their name. If a summary names the proxy,
  write "you" (for example "You own the final mockups").
- The person on leave is away during this meeting: never tell the proxy to check with them or wait for them.
- Write open items as what the proxy may need to raise, decide or confirm in the meeting on the absent person's behalf.
- For "check_with", suggest the organizer (or another person named in the input), never the proxy or the person on leave.
- Refer to other people by first name."""


def build_prompt(event: CalEvent, absent: Person, notes: list[Note], proxy: Optional[Person],
                 organizer: Optional[Person] = None) -> str:
    """Everything Gemini is shown. `notes` must already be the summaries both the sender and the proxy may open."""
    return (
        f"Meeting: {event.title}\n"
        f"Date: {event.start.date().isoformat()}\n"
        f"Description: {event.description or '(none)'}\n"
        f"Organizer: " + (f"{organizer.name} ({organizer.title})" if organizer else "(unknown)") + "\n"
        f"Person on leave: {absent.name} ({absent.title})\n"
        f"Proxy: " + (f"{proxy.name} ({proxy.title})" if proxy else "(not named)") + "\n"
        f"Previous summaries:\n" + "\n".join(f"- {n.text}" for n in notes)
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


def _check_with(text: str, absent: Person, proxy: Optional[Person], organizer: Optional[Person]) -> str:
    """Plain-code check: never send the proxy to themselves or to the person who is away."""
    text = text.strip()
    bad = {absent.name.split()[0].lower()} | ({proxy.name.split()[0].lower()} if proxy else set())
    if text and not any(re.search(rf"\b{re.escape(b)}\b", text.lower()) for b in bad):
        return text
    if organizer and organizer.id != absent.id and (not proxy or organizer.id != proxy.id):
        return f"If anything is unclear, check with {organizer.name.split()[0]}, who organizes the meeting."
    return "If anything is unclear, reply to this note."


def render(brief: HandoverBrief, event: CalEvent, absent: Person, proxy: Optional[Person],
           organizer: Optional[Person] = None) -> str:
    """Our code writes the greeting and layout; the AI only fills the content. Plain-code checks happen here."""
    clean = lambda items, cap: [s.strip() for s in items if s and s.strip()][:cap]   # noqa: E731
    points = clean(brief.key_points, S.drafter.max_key_points)
    open_items = clean(brief.open_items, S.drafter.max_open_items)
    first = absent.name.split()[0]
    hello = f"Hi {proxy.name.split()[0]}," if proxy else "Hi,"
    when = event.start.strftime("%a %d %b")
    parts = [f"{hello} thanks for covering '{event.title}' on {when} for {first}.", "",
             brief.meeting_purpose.strip(), brief.covering_for.strip()]
    if points:
        parts += ["", "Key points from earlier meetings:"] + [f"- {p}" for p in points]
    if open_items:
        parts += ["", "Still open:"] + [f"- {p}" for p in open_items]
    parts += ["", _check_with(brief.check_with, absent, proxy, organizer)]
    return "\n".join(p for p in parts if p is not None).strip()


def draft_note(event: CalEvent, absent: Person, notes: list[Note], proxy: Optional[Person] = None,
               client: Any = None, organizer: Optional[Person] = None) -> tuple[str, str]:
    """Returns (text, engine): engine "gemini", "rules" (AI off) or "rules_fallback" (Gemini failed).
    `client` is only for tests (a fake that returns a ready answer without calling Google)."""
    if not S.ai.enabled:
        return draft_note_rules(event, absent, notes), "rules"
    from .orchestrator import _with_retries
    try:
        brief = _with_retries(lambda: ask_gemini(build_prompt(event, absent, notes, proxy, organizer), client))
        return render(brief, event, absent, proxy, organizer), "gemini"
    except Exception as err:   # noqa: BLE001 - the sender must always get a draft
        log.warning("AI note draft failed for '%s' (%s): using the simple draft", event.title, err)
        return draft_note_rules(event, absent, notes), "rules_fallback"
