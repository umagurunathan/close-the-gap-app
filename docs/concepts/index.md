---
type: Section Index
title: Concepts
description: Navigation hub for the domain vocabulary — meeting kinds, actions, status, and hardcoded product rules.
tags: [concepts, navigation]
timestamp: 2026-10-15T00:00:00Z
---

# Concepts

- [Meeting kinds](meeting-kinds.md) — `key_meeting`, `team_checkin`, `org_event`, and how the
  guard layer decides which one applies.
- [Actions](actions.md) — the five actions, who may choose each one, and the resulting item
  status.
- [Product rules](product-rules.md) — the rules that are hardcoded on purpose and will never be a
  config knob, plus where in the code they're enforced.

See also: [Architecture → Item lifecycle](../architecture/item-lifecycle.md) for how these pieces
compose into a running state machine.
