---
type: Component
title: Item lifecycle
description: How a MeetingItem is created, auto-resolved or decided, and acted on.
resource: backend/app/service.py
tags: [architecture, lifecycle, meetingitem]
timestamp: 2026-10-15T00:00:00Z
---

# Item lifecycle

A `MeetingItem` is one card: (one affected meeting, one absent person). It's the central unit the
whole app revolves around.

## Creation

Two entry points trigger the same scan:

```
create_absence(person, start, end)  ──▶ Service._scan(absence)
                                            → for every event in the window where the person
                                              is a key person: Service._create_item(...)

schedule_meeting(...) / add_attendee(...)  ──▶ Service._scan_event(event)
                                            → for every key person already on an absence that
                                              covers this meeting's day: Service._create_item(...)
```

Both converge on `Service._create_item(absence, absent, event, now)`
([backend/app/service.py:115](../../backend/app/service.py)), which:

1. Skips if the meeting is already over, or a card for `(this meeting, this absent person)`
   already exists.
2. Sets `ownerRole`: `"leaver"` for a planned absence, `"organizer"` for a sudden one — this
   decides who the *default* decider is (see [concepts/actions.md](../concepts/actions.md)).
3. Calls `Service._analyze` (see
   [recommendation-pipeline.md](recommendation-pipeline.md)) with `allow_ai =
   [ai].analyse_on_creation` (default `false`, so creation never waits on a network call) to get
   the item's `kind` and `ai` block.
4. If `kind != key_meeting` (i.e. `team_checkin` or `org_event`), the item is immediately
   `auto_handled` with `chosenAction = proceed_without` — nobody needs to look at it.
5. Logs an `item_created` history entry and stores the item.

### Scheduling into an absence

If a meeting is scheduled (or a key person added) while someone is *already* out, the same flow
starts at once (`Service.schedule_meeting` / `Service.add_attendee` → `_scan_event`) and the
organizer gets **one** email naming everyone affected, however many key people turned out to be
out.

## Viewing

`Service._view(item, viewer)` computes per-viewer, non-persisted fields at list time — nothing
here is stored on the item:

- `needsAttention`: `status` is in the "not yet settled" set and the meeting hasn't passed.
- `urgency`: `"soon"` (≤ `urgency.soon_hours`, default 72h) or `"urgent"` (≤ `urgency.urgent_hours`,
  default 24h), only while `needsAttention`.
- `hoursToStart`.
- `ai`: freshly resolved via `Service._analyze(item, viewer)` — this is why the same item can show
  a different recommendation to different viewers (bounded by the
  [privacy rule](privacy-rule.md)).

## Status transitions

`Service.apply_action` is the **single place** state transitions happen. It validates who may act
(`{absentPersonId} | organizer_side`), then branches on the `Action`:

| Action | Resulting status | Notes |
|---|---|---|
| `attend` | `attending` | Only the leaver, only on their own planned-leave items. |
| `proceed_without` | `proceeding_without` | Either side. |
| `proxy` | `proxy_requested` → `proxy_accepted` / `proxy_declined` (via `respond_proxy`) | Proxy need not be an invitee; if not, they're added to the meeting as optional. Choosing a new proxy withdraws any earlier request. |
| `reschedule` (organizer) | `rescheduled` via `scheduling.find_slot` | `no_slot_found` if the search comes up empty. |
| `reschedule` (non-organizer) | `awaiting_organizer` | Only the organizer can actually move the meeting; a non-organizer's choice becomes a task for them. |
| `cancel` (organizer) | `cancelled` | |
| `cancel` (non-organizer) | `awaiting_organizer` | Same reasoning as reschedule. |

Terminal statuses (`rescheduled`, `cancelled`) reject any further action. Every transition is
logged to history and, where it matters to someone, emits an email via `notify.send_email` — see
[backend/app/notify.py](../../backend/app/notify.py).

See [concepts/actions.md](../concepts/actions.md) for the full action/status vocabulary and
[concepts/meeting-kinds.md](../concepts/meeting-kinds.md) for what `kind` means.
