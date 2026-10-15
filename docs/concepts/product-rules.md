---
type: Concept
title: Product rules
description: Rules that are hardcoded on purpose and must never become a config.toml knob.
resource: backend/config/settings.toml
tags: [concepts, decision, rules]
timestamp: 2026-10-15T00:00:00Z
---

# Product rules (hardcoded, not configurable)

`config/settings.toml`'s header comment lists the product rules that are deliberately **not** in
that file, because they're invariants, not tuning knobs. Weakening any of these by config would be
a product or privacy bug, not a legitimate variant — so they're enforced in code:

| Rule | Enforced in |
|---|---|
| A person's AI recommendation only reads summaries that person can open. | [`app/calendar.py:visible_notes`](../../backend/app/calendar.py); see [privacy-rule.md](../architecture/privacy-rule.md). |
| "The AI proposes, a person decides" — `attend` is never AI-recommended. | [`agents/guard.py`](../../backend/agents/guard.py) rule 4; see [actions.md](actions.md). |
| Only the organizer can actually reschedule or cancel a meeting. | [`Service.apply_action`](../../backend/app/service.py) — a non-organizer's choice becomes `awaiting_organizer`. |
| One occurrence at a time (no recurring-series-wide actions). | `MeetingItem.event.instanceStart` / `Service._create_item` operate per calendar event instance. |
| Optional attendees never trigger anything. | [`app/scheduling.py:key_people`](../../backend/app/scheduling.py) and `Service._scan_event` only check required attendees + organizer. |
| Who counts as a "key person" = the organizer plus required (non-optional) attendees. | Same `key_people` function, shared by scanning and rescheduling so the definition can't drift between the two. |
| There is exactly one set of five actions (`attend`, `proceed_without`, `proxy`, `reschedule`, `cancel`) — no per-meeting-kind variants. | [`app/models.py:Action`](../../backend/app/models.py). |

Contrast this with `config/settings.toml`, which holds genuinely tunable numbers and word lists
(reminder milestones, urgency thresholds, the reschedule window, proxy ranking weights, AI
model/thresholds) — see [config/settings.md](../config/settings.md). The distinction is the
load-bearing design choice: tunables can be edited and restarted with no code change; rules here
cannot be changed without changing the code (and reviewing why).
