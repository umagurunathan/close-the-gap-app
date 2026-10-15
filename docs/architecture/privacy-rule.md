---
type: Decision
title: Privacy rule
description: The load-bearing rule that a recommendation is built only from what its viewer could already open.
resource: backend/app/calendar.py
tags: [architecture, privacy, decision]
timestamp: 2026-10-15T00:00:00Z
---

# Privacy rule (load-bearing — don't break it)

A person's recommendation is built **only** from meeting summaries that person can open.

> "open" = `SimCalendar.visible_notes(event, viewer_id)`: shared with the viewer, or the viewer is
> the organizer. See [`backend/app/calendar.py:37`](../../backend/app/calendar.py).

## Why it's load-bearing

- Nothing from a summary ever reaches someone who couldn't open it in the calendar — not in the
  recommendation text, not in the sources list, not in a drafted handover note.
- A missing summary never *blocks* a recommendation; it just lowers confidence (see
  `agents/recommender.py` branch 4, and `[ai].max_confidence_for_proxy_without_summaries` in
  [config/settings.md](../config/settings.md)).
- This is why `Service._analysis_cache`'s key includes the fingerprint of the *viewer's own*
  visible notes (not the event's notes in general) — two viewers with different visibility must
  never share a cached answer. See
  [recommendation-pipeline.md#caching](recommendation-pipeline.md#caching).

## Where it's enforced

Every caller that touches a meeting's notes goes through `visible_notes` first, then passes only
that filtered list downstream:

- `Service._analyze` → `agents.orchestrator.analyze` → both `recommend` (rules) and
  `recommend_ai` (Gemini) only ever see the filtered `notes` argument.
- `Service._openly_shared_notes` (used for proxy-request emails and AI-drafted handover notes)
  additionally restricts to notes shared with *everyone* invited, not just the caller — a stricter
  subset of the privacy rule, used because a note sent to a proxy must not reveal anything the
  proxy couldn't otherwise see.
- `Service.proxy_candidates` ranks proxies using `calendar.visible_notes(e, caller)` — the
  *caller's* view, not the absent person's.

## Deliberately not a config knob

This rule is deliberately **not** tunable in `config/settings.toml` — see that file's header
comment. It's enforced in code, not configuration, because a tuning mistake here would be a data
leak, not a UX regression. The other product rules that are hardcoded for the same reason are
listed in [concepts/product-rules.md](../concepts/product-rules.md).
