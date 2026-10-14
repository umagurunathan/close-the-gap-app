r"""See Gemini's recommendation for one of Priya's demo meetings, next to the rule-based stand-in's.

Run from the backend folder:
    .\.venv\Scripts\python.exe scripts\structured_demo.py "Q4 Budget Review"
    .\.venv\Scripts\python.exe scripts\structured_demo.py "Daily Stand-up"
    .\.venv\Scripts\python.exe scripts\structured_demo.py "Site-wide Tech Talk: Cloud Cost Optimization"
    .\.venv\Scripts\python.exe scripts\structured_demo.py "Vendor Contract Decision"
    add  --model NAME  to try another model

It uses the real agent code (agents/recommender_ai.py): the same prompt, schema and instructions the app uses.
The check at the end is a small preview of the checking layer (C).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.config  # noqa: F401  (loads backend/.env)
from agents.recommender import recommend  # noqa: E402  (the rule-based stand-in)
from agents.recommender_ai import ask_gemini, build_prompt, candidates_for, to_ai_result  # noqa: E402
from app.models import Action, Confidence  # noqa: E402
from app.seed import build_service  # noqa: E402
from app.settings import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("title", help="exact title of one of Priya's meetings")
    parser.add_argument("--model", default=None, help="override [ai] model from settings.toml")
    args = parser.parse_args()
    if args.model:
        settings.ai.model = args.model

    svc = build_service()
    absent = svc.person("p_priya")
    item = next((i for i in svc.store.items() if i.absentPersonId == absent.id and i.event.title == args.title), None)
    if not item:
        sys.exit("No such meeting for Priya. Titles: " + ", ".join(i.event.title for i in svc.store.items() if i.absentPersonId == absent.id))
    event = svc.calendar.get(item.event.calendarEventId)
    people = svc.people_map()
    notes = svc.calendar.visible_notes(event, absent.id)   # privacy: only what she may open

    prompt = build_prompt(event, absent, people, notes)
    answer = ask_gemini(prompt)   # a real Python object, not text

    print(f"=== What Gemini was shown (model: {settings.ai.model}) ===")
    print(prompt)
    print("\n=== Gemini's structured answer ===")
    print(answer.model_dump_json(indent=2))

    # A small preview of layer C: plain code checking the answer against our rules.
    problems = []
    candidate_ids = {c.id for c in candidates_for(event, absent, people)}
    if answer.suggested_proxy_id and answer.suggested_proxy_id not in candidate_ids:
        problems.append(f"suggested_proxy_id '{answer.suggested_proxy_id}' is not one of the candidates")
    if answer.recommendation == Action.proxy and not answer.suggested_proxy_id and not answer.needs_human_choice:
        problems.append("a proxy was recommended but nobody was named and no human choice was requested")
    if answer.recommendation == Action.attend:
        problems.append("'attend' may only be chosen by the person themselves")
    if answer.recommendation == Action.proxy and answer.suggested_proxy_id and not notes and answer.confidence != Confidence.low:
        problems.append("a proxy chosen with no summaries to support it should be low confidence (reporting line only)")
    print("\n=== Check (preview of layer C) ===")
    print("OK" if not problems else "PROBLEMS: " + "; ".join(problems))

    kind, card = to_ai_result(answer, notes)
    print("\n=== What the card would hold ===")
    print(f"kind={kind.value}  sources={card.sources}  summariesAvailable={card.summariesAvailable}")

    stub_kind, stub = recommend(event, absent, people, notes)
    print("\n=== The rule-based stand-in said ===")
    print(f"kind={stub_kind.value}  action={stub.recommendation.value if stub.recommendation else None}  "
          f"proxy={stub.suggestedProxyId}  confidence={stub.confidence.value}")
    print(f"reason: {stub.reason}")


if __name__ == "__main__":
    main()
