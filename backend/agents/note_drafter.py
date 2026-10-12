"""Draft a handover note for a proxy.

STUB: rule-based so the app runs with no AI key. Replace `draft_note` with a Gemini call that returns the same
kind of text. Keep the signature.

Important rule (enforced by the caller, Service.note_draft): this is only ever called with summaries the host shared
with everyone invited. The sender reads and edits the draft before sending.
"""
from __future__ import annotations

import re

from app.models import CalEvent, Note, Person

KEY_WORDS = ("decid", "decision", "approve", "owns", "owner", "action item", "to confirm", "sign off", "sign-off", "to prepare")


def draft_note(event: CalEvent, absent: Person, notes: list[Note]) -> str:
    first = absent.name.split()[0]
    sentences: list[str] = []
    for n in notes:
        for s in re.split(r"(?<=[.!?])\s+", n.text.strip()):
            low = s.lower()
            if s and (first.lower() in low or any(k in low for k in KEY_WORDS)) and s not in sentences:
                sentences.append(s)
    if not sentences and notes:
        sentences = re.split(r"(?<=[.!?])\s+", notes[0].text.strip())[:2]
    bullets = "\n".join(f"- {s}" for s in sentences[:5])
    return (
        f"Hi, thanks for covering '{event.title}' for {first}.\n"
        f"From the previous summaries:\n{bullets}\n"
        f"Please check with {first} if anything is unclear."
    )
