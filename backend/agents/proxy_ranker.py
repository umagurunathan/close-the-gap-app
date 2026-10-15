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
from app.settings import settings as S


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
    who = absent.name.split()[0]
    for pid in invitees:
        p = people.get(pid)
        if not p or p.isGroup:  # distribution lists can't cover a meeting
            continue
        score, reasons = 0, []
        mentions = text.count(_first_name(p)) if text else 0
        if mentions:
            score += S.proxy_ranking.named_in_summaries_base + mentions
            reasons.append("mentioned in an earlier summary" if mentions == 1 else f"mentioned {mentions} times in earlier summaries")
        if absent.managerId == pid:
            score += S.proxy_ranking.absent_persons_manager
            reasons.append(f"{who}'s manager")
        elif p.managerId and p.managerId == absent.managerId:
            score += S.proxy_ranking.peer_same_manager
            reasons.append(f"{who}'s peer (same manager)")
        elif p.managerId == absent.id:
            score += S.proxy_ranking.direct_report
            reasons.append(f"reports to {who}")
        # shown on screen next to the person: plain words, sentence case
        reason = " · ".join(reasons) or "invited, no other link found"
        scored.append((score, pid, reason[0].upper() + reason[1:]))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"personId": pid, "rank": i + 1, "reason": reason, "score": score}
            for i, (score, pid, reason) in enumerate(scored)]
