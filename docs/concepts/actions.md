---
type: Product Concept
title: The five actions
description: attend, proceed_without, proxy, reschedule and cancel; who may take each, what each does to the card and the meeting, and which the AI may recommend.
resource: ../../backend/app/service.py
tags: [actions, decisions, core]
sources:
  - resource: ../../backend/app/models.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/agents/guard.py
  - resource: ../../web/src/components/MeetingCard.jsx
  - resource: ../../web/src/components/OrganizerCard.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# The five actions (`Action`)

There is **one fixed action set**. It is a product rule, not a setting (see [Product rules](product-rules.md)). Every decision is one of these five, applied through `Service.apply_action` (one card) or `Service.apply_meeting_action` (the whole meeting).

| Action | UI label | Who may take it | Resulting status | Side effects |
|---|---|---|---|---|
| `attend` | "I'll attend" | Only the absent person, and only on a `leaver` (planned) card | `attending` | FYI email to the organizer |
| `proceed_without` | "Go on without me" / "Go on without {name}" | Absent person or organizer side | `proceeding_without` | Open proxy requests are withdrawn silently |
| `proxy` | "Ask {name} to cover" / "Choose a proxy" | Absent person or organizer side | `proxy_requested` | Creates a `ProxyRequest`, emails the proxy, may add the proxy to the invite. See [Proxy](proxy.md) |
| `reschedule` | "Reschedule" (organizer) / "Ask to reschedule" | Organizer side moves the meeting; anyone else's choice becomes a request | `rescheduled`, `no_slot_found`, or `awaiting_organizer` | Google event moved first; one move for everyone. See [Reschedule search](../architecture/reschedule-search.md) |
| `cancel` | "Cancel this meeting" / "Ask to cancel" | Organizer side cancels; anyone else's choice becomes a request | `cancelled` or `awaiting_organizer` | Google event deleted once |

## Which actions the AI may recommend

- The AI may recommend `proceed_without`, `proxy`, `reschedule` or `cancel`. It is told to **prefer a proxy** when the absent person owns an item that a suitable candidate can cover. It should recommend reschedule only when the input says the meeting cannot work without the person, and cancel rarely.
- **`attend` is never recommended.** Only the person themselves can choose it. If the AI answers `attend`, guard rule 4 replaces the whole answer with the rules' answer (engine `rules_override`).

## Whole-meeting actions (Organizer Mode)

`POST /meetings/{event_id}/action` (`apply_meeting_action`) accepts only `reschedule`, `cancel` or `proceed_without`. A proxy is always chosen per person, on that person's row.

- **`proceed_without`** applies only to undecided cards: `pending_decision`, `proxy_declined`, `no_slot_found` and `awaiting_organizer`. A pending or accepted proxy, or "I'll attend", is kept.
- **`cancel`** applies to every open card.
- **`reschedule`** makes **one move** for everyone, to the proposed time or the organizer's picked time. If no time is found, every open card is marked `no_slot_found`.

## Changing a decision

A decision can be changed until the card is terminal (`rescheduled` or `cancelled`). If someone overrides a decision the *other* side already made (the previous status was not `pending_decision` or `auto_handled`), the previous decider is emailed "X changed the decision for '…'".

## Related
- [Decide on a card flow](../flows/decide-on-a-card.md)
- [Permissions](permissions.md)
- [Meeting card](meeting-card.md)
