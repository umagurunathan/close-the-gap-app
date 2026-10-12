"""Proxy ranker specialist.

STUB: rule-based so the app runs with no AI key. Replace the body of `rank_proxies` with an ADK/Gemini
agent that returns the same list. Keep the signature and the return shape.

Rules it follows:
- The AI suggests only from existing invitees, excluding the absent person. (A person choosing a proxy can also search the whole directory; that is not the AI's call.)
- Evidence order: previous meeting summaries first; reporting hierarchy only as a fallback.
- Never guess: no candidates -> empty list (the app then asks a human to choose).
"""
from __future__ import annotations

from app.models import CalEvent, Note, Person


def _first_name(p: Person) -> str:
    return p.name.split()[0].lower()


def rank_proxies(
    event: CalEvent,
    absent: Person,
    people: dict[str, Person],
    notes: list[Note],
) -> list[dict]:
    invitees = [a.personId for a in event.attendees if a.personId != absent.id]
    if event.organizerId != absent.id and event.organizerId not in invitees:
        invitees.append(event.organizerId)
    scored = []
    text = " ".join(n.text.lower() for n in notes)
    for pid in invitees:
        p = people.get(pid)
        if not p or p.isGroup:  # distribution lists can't cover a meeting
            continue
        score, reasons = 0, []
        mentions = text.count(_first_name(p)) if text else 0
        if mentions:
            score += 10 + mentions
            reasons.append(f"named {mentions}x in previous summaries")
        if absent.managerId == pid:
            score += 3
            reasons.append("the absent person's manager")
        elif p.managerId and p.managerId == absent.managerId:
            score += 2
            reasons.append("a peer (same manager)")
        elif p.managerId == absent.id:
            score += 2
            reasons.append("a direct report")
        scored.append((score, pid, "; ".join(reasons) or "invitee, no supporting evidence"))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"personId": pid, "rank": i + 1, "reason": reason, "score": score}
            for i, (score, pid, reason) in enumerate(scored)]
