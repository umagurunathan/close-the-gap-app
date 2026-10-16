"""FALLBACK ONLY: plain rules used when the AI is switched off or Gemini is unavailable (and by the tests).

The product's judgment runs on Gemini: the ADK meeting advisor (agents/adk_advisor.py), the single-call recommender
(agents/recommender_ai.py) and the handover brief (agents/note_drafter.py), all checked by agents/guard.py.
These rules keep the app working without the AI, and show on each card what simple rules alone would have said,
so the difference the AI makes is visible.

- rules_recommender.py: keyword rules for the kind of meeting and the action.
- candidate_order.py:   orders the proxy list in the panel (named in summaries, then the reporting line).
- simple_note.py:       a handover note made of the summary sentences that mention the person or a decision.
"""
