"""FALLBACK ONLY (AI off, or Gemini failed): a simple handover note without AI.

The sentences of the summaries that mention the absent person or a decision word (`[drafter] key_words` in
config/settings.toml). Kept so the sender always gets a draft; the panel then says "Simple draft · AI unavailable".
The Gemini brief is in agents/note_drafter.py.
"""
from __future__ import annotations

import re
from typing import Optional

from app.models import CalEvent, Note, Person
from app.settings import settings as S


def draft_note_rules(event: CalEvent, absent: Person, notes: list[Note], proxy: Optional[Person] = None,
                     organizer: Optional[Person] = None) -> str:
    from ..note_drafter import _ask_organizer, _greeting   # same greeting and closing as the Gemini brief
    first = absent.name.split()[0]
    key_words = tuple(S.drafter.key_words)
    sentences: list[str] = []
    for n in notes:
        for s in re.split(r"(?<=[.!?])\s+", n.text.strip()):
            low = s.lower()
            if s and (first.lower() in low or any(k in low for k in key_words)) and s not in sentences:
                sentences.append(s)
    if not sentences and notes:
        sentences = re.split(r"(?<=[.!?])\s+", notes[0].text.strip())[:S.drafter.fallback_sentences]
    bullets = "\n".join(f"- {s}" for s in sentences[:S.drafter.max_bullets])
    return (f"{_greeting(event, absent, proxy)}\n\n"
            f"From the previous summaries:\n{bullets}\n\n"
            f"{_ask_organizer(absent, proxy, organizer)}")
