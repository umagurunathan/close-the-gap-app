---
type: Section Index
title: Architecture
description: Navigation hub for how the backend and frontend are put together.
tags: [architecture, navigation]
timestamp: 2026-10-15T00:00:00Z
---

# Architecture

- [Backend](backend.md) — the FastAPI → Service → agents/adapters layering, and the adapter
  pattern used for the calendar and the store.
- [Frontend](frontend.md) — the single-page React app, its one fetch wrapper, and its four tabs.
- [Recommendation pipeline](recommendation-pipeline.md) — how one affected meeting gets turned
  into a recommendation: rules, Gemini, the guard layer, and the fallback path.
- [Privacy rule](privacy-rule.md) — the one architectural rule that must never be broken: a
  recommendation is built only from what its viewer could already open.
- [Item lifecycle](item-lifecycle.md) — how a `MeetingItem` is created, viewed, and resolved.

See also: [Concepts](../concepts/index.md) for the domain vocabulary these components manipulate
(actions, meeting kinds, statuses).
