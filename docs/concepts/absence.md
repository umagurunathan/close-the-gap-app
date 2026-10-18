---
type: Product Concept
title: Absence
description: A person out for one or more whole days; planned or sudden (less than 24 hours' notice), which decides who owns the resulting cards and who is emailed.
resource: ../../backend/app/service.py
tags: [absence, leave, core]
sources:
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/models.py
  - resource: ../../backend/app/main.py
  - resource: ../../backend/config/settings.toml
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Absence

An **absence** says that a person is out from `start` to `end`. Both are whole dates and both are inclusive. Saving one starts the scan that creates [meeting cards](meeting-card.md). It is the trigger for most of what the app does.

## Shape (`app/models.py` → `Absence`)

| Field | Meaning |
|---|---|
| `id` | `a_…` |
| `personId` | Who is out |
| `start`, `end` | Dates, inclusive. `end < start` is rejected |
| `type` | `planned` or `sudden`. Derived by the server; never sent by the client |
| `source` | `manual` (Report an absence), `leave_system` (dev simulator), `calendar_ooo` (seed only; Calendar OOO is not read as an absence) |
| `enteredBy` | Who reported it |
| `createdAt` | When it was saved |

## Planned vs sudden

`Service.absence_type(start)`: the absence is **sudden** if `start` at 00:00 UTC is `[absence] sudden_notice_hours` (24) hours or less away, or has already passed. Otherwise it is **planned**. A sick day booked a month ahead is planned.

The type changes three things:

| | Planned | Sudden |
|---|---|---|
| Card `ownerRole` | `leaver`: the absent person owns it | `organizer`: the organizer side owns it |
| Who is emailed at creation | The absent person, with a summary | The absent person, **and** each organizer-side decider at once ("X is out suddenly…") |
| "I'll attend" offered | Yes, to the absent person | No |
| Later organizer alert | Under-24-hour alert if still unresolved | Already alerted (`organizerAlerted = True`) |

Either way, **both sides may act** on the card. See [Permissions](permissions.md).

The seed forces Kiran's absence to `"type": "sudden"`. The demo runs on the real clock, so by date it would be weeks away. See [Seed world](../data/seed-world.md).

## Rules

- **Own absence only.** `POST /absences` returns 403 unless `body.personId` is the caller. This applies in both areas.
- **Day matching is in UTC.** A meeting is affected when its `start` date (UTC) falls within `start..end` (`SimCalendar.events_in_window`).
- **Overlapping absences do not create duplicate cards.** There is at most one card per *(meeting, absent person)*. The confirmation still counts the cards on those days (`cards_on_days`).
- **Optional invitees are skipped.** A meeting where the person is only optional creates no card.
- Absences shown to a person are the current and upcoming ones only (`end >= today`), earliest first (`absences_for`).

## Where in the code
- `Service.report_absence`, `absence_type`, `_scan`, `cards_on_days` and `absences_for` in `app/service.py`
- `post_absence` (`POST /absences`) and `simulate_leave_system` (`POST /dev/simulate-leave-system`, demo only) in `app/main.py`

## Related
- [Report an absence flow](../flows/report-an-absence.md)
- [Meeting card](meeting-card.md)
- [Notifications and reminders](../architecture/notifications-and-reminders.md)
