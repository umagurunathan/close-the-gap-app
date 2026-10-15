---
type: Component
title: Recommendation pipeline
description: How one affected meeting becomes a card's recommendation — rules, Gemini, the guard layer, and the fallback path.
resource: backend/agents/orchestrator.py
tags: [architecture, ai, gemini, agents]
timestamp: 2026-10-15T00:00:00Z
---

# Recommendation pipeline

One entry point, [`agents/orchestrator.py:analyze()`](../../backend/agents/orchestrator.py),
called from `Service._analyze`. It takes one affected meeting plus the viewer who will decide, and
returns `(ItemKind, AiResult)` — the whole AI block shown on a card.

## Flow when `[ai] enabled = true`

```
Service._analyze(item, viewer)
     │
     ▼
agents.orchestrator.analyze(event, absent, viewer, people, calendar, is_out, use_ai)
     │
     ├─ 1. agents/recommender_ai.py: ask Gemini (Vertex AI, ADC credentials, no API key)
     │       for a structured `Recommendation` (fixed pydantic schema — nothing is parsed
     │       or guessed from free text).
     │
     ├─ 2. Temporary failures (429, 5xx, timeouts) retried [ai].attempts times, waiting
     │       [ai].retry_wait_seconds between tries. Non-temporary errors are not retried.
     │
     ├─ 3. agents/guard.py ("layer C"): the answer is checked against product rules by
     │       plain code — see "The guard layer" below. Every correction is recorded in
     │       `AiResult.checks`.
     │
     └─ 4. If Gemini is still unavailable after retries, the rule-based answer
             (agents/recommender.py) is used instead, labelled `engine = "rules_fallback"`.
```

**The AI can therefore never block or break the app** — every exit from this flow produces a
usable `AiResult`.

When `[ai] enabled = false` (the default; used by tests — no network),
[`agents/recommender.py`](../../backend/agents/recommender.py) and
[`agents/proxy_ranker.py`](../../backend/agents/proxy_ranker.py) decide instead. They are
rule-based stand-ins with the **same function signature** as their AI counterparts
(`recommend_ai`, `rank_proxies`), so swapping which one runs is a one-line config flip in
[`config/settings.toml`](../../backend/config/settings.toml).

## `AiResult.engine`

Every card's `engine` field tells you which path produced it:

| `engine` | Meaning |
|---|---|
| `gemini` | Gemini answered, possibly adjusted by the guard layer (see `checks`). |
| `rules` | `[ai] enabled = false` — the rule-based stand-in decided. |
| `rules_fallback` | Gemini was unavailable after retries; the rule-based answer was used and labelled "AI unavailable". |
| `rules_override` | The guard layer rejected the AI's answer outright (currently: it recommended `attend`) and substituted the rule-based answer wholesale. |

## The guard layer (`agents/guard.py`)

The schema already guarantees the *shape* of Gemini's answer. `guard.check()` guarantees the
*rules* that must never be broken, whatever the model said:

1. A suggested proxy must be one of the real candidates (an individual invitee or the organizer,
   never the absent person or a group) and must not be out of office that day — otherwise the
   suggestion is dropped and a person must choose.
2. A `proxy` recommendation with nobody named sets `needsHumanChoice = true`.
3. A proxy chosen with no supporting summaries is capped at
   `[ai].max_confidence_for_proxy_without_summaries` (it rests on the reporting line only). A
   conclusion from the title or agenda alone is *not* capped.
4. `attend` is never recommended by the AI — only the person themselves can choose it. If Gemini
   returns it anyway, the whole answer is replaced by the rule-based one (`engine =
   "rules_override"`).
5. A `team_checkin` needs summaries showing status updates only; without summaries it reverts to
   `key_meeting`.
6. Auto-handling (`team_checkin` / `org_event`) requires confidence at least
   `[ai].auto_handle_requires`; below that, it becomes a `key_meeting`.
7. An org-wide event the absent person organizes or hosts is a `key_meeting`, not an `org_event`
   ("Decision 48").

Every correction made here is appended to `ai.checks` in plain words, so it's visible on the card
and auditable later — it's the one place you can see exactly where the AI's answer was overridden
and why.

## Caching

`Service._analysis_cache` keys on `(item id, meeting fingerprint, visible-notes fingerprint, ai
config)`. Consequences:

- The AI is only asked again when the meeting or the summaries *that viewer* can see actually
  change.
- Two viewers who can see the same documents share one cached result.
- Only a "final" answer is cached — Gemini's when AI is on, the rules' when it's off. A fallback
  answer, or the placeholder made while creating a card (`[ai].analyse_on_creation = false`), is
  **not** cached, so the real AI is asked the first time the card is actually viewed rather than
  at absence-creation time (which would otherwise block startup/creation on a network call).

See also: [item-lifecycle.md](item-lifecycle.md) for when `_analyze` gets called, and
[privacy-rule.md](privacy-rule.md) for how `notes` is restricted before it ever reaches this
pipeline.
