---
type: Concept
title: Actions
description: The five actions a person can choose for an affected meeting, who may choose each, and the resulting status.
resource: backend/app/models.py
tags: [concepts, action, itemstatus]
timestamp: 2026-10-15T00:00:00Z
---

# Actions (`Action`)

Five actions, defined in [backend/app/models.py:22](../../backend/app/models.py) and applied
through the single `Service.apply_action` ([backend/app/service.py:330](../../backend/app/service.py)):

| Action | "I'll attend" wording | Who may choose it | Resulting `ItemStatus` |
|---|---|---|---|
| `attend` | "I'll attend" | Only the leaver, only on their own planned-leave `key_meeting` items. | `attending` |
| `proceed_without` | "Go on without me" | Either side (leaver or organizer side). | `proceeding_without` |
| `proxy` | — | Either side. The proxy can be anyone in the company directory, invited or not. | `proxy_requested` → `proxy_accepted` / `proxy_declined` |
| `reschedule` | — | Anyone can *request* it; only the organizer can actually move the meeting. | `rescheduled` (organizer) or `awaiting_organizer` (anyone else) |
| `cancel` | — | Same as reschedule. | `cancelled` (organizer) or `awaiting_organizer` (anyone else) |

`attend` is special in one more way: it is **never AI-recommended** (see
[architecture/recommendation-pipeline.md](../architecture/recommendation-pipeline.md#the-guard-layer-agentsguardpy)
rule 4) — only the person themselves can choose it, so the AI is not allowed to suggest it for
them.

## Who may act (`may_act`)

For every item, `{item.absentPersonId} | organizer_side` may act, where `organizer_side` is
normally `{event.organizerId}`, plus the absent person's manager when the organizer *is* the
absent person (`ownerRole == "organizer"`, i.e. a sudden absence where the organizer themselves is
out — see [architecture/item-lifecycle.md](../architecture/item-lifecycle.md#creation)).

## `ItemStatus` reference

The full status enum ([backend/app/models.py:42](../../backend/app/models.py)):

`pending_decision` → `auto_handled` | `attending` | `proceeding_without` | `proxy_requested` →
(`proxy_accepted` | `proxy_declined`) | `awaiting_organizer` | `rescheduled` | `cancelled` |
`no_slot_found`

- **Terminal** (no further action possible): `rescheduled`, `cancelled`.
- **Resolved** (counted in `Service.metrics()`): `auto_handled`, `attending`,
  `proceeding_without`, `proxy_accepted`, `rescheduled`, `cancelled`.
- **Needs attention** (drives the amber/red urgency chips): `pending_decision`,
  `proxy_requested`, `awaiting_organizer`, `proxy_declined`, `no_slot_found`.

If someone changes a decision the *other* side already made, that person is emailed once — no
email otherwise (`Service.apply_action`'s `previous_decider` check).
