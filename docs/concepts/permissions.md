---
type: Policy
title: Who may do what
description: Permissions come from each person's relationship to a card (absent person, organizer side, invitee, named proxy), not from a role system; the full matrix and where it is enforced.
resource: ../../backend/app/service.py
tags: [permissions, authorization, policy]
sources:
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/main.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Who may do what

There is **no role enum** (no admin or manager role). Every permission comes from the caller's **relationship to the card or meeting**:

- **Absent person**: `item.absentPersonId`.
- **Organizer side**: the meeting's `organizerId`, always, also when the organizer is the one who is out (`Service._organizer_side`, `organizer_decider`). Nobody else, not even the organizer's manager, can move or cancel the meeting. If the organizer and another key person are both out and nothing was decided, the invitees are told shortly before the meeting so they can agree by email (see [Notifications](../architecture/notifications-and-reminders.md)).
- **Invitee**: an attendee or the organizer.
- **Named proxy**: the `proxyId` of a request.

Checks raise `PermissionError` in `Service`. The `guard()` wrapper in `app/main.py` turns that into **HTTP 403**.

## Matrix

| What | Who | Enforced in |
|---|---|---|
| Act on a card (any action) | Absent person **or** organizer side, for planned and sudden absences alike | `apply_action` |
| "I'll attend" | Absent person only, on a `leaver` card only | `apply_action` |
| Actually reschedule or cancel | Organizer side. Anyone else's choice becomes `awaiting_organizer` and the organizer is emailed | `apply_action` |
| Whole-meeting action | Organizer side of any of the meeting's cards | `apply_meeting_action` |
| Proxy candidates, proposed time, note-draft availability, AI draft | Absent person or organizer side | `proxy_candidates`, `proposed_time`, `_draft_notes` |
| Read meeting summaries and agenda | Invitees, and each summary is further filtered by `sharedWith` | `meeting_notes`, `meeting_agenda`, `SimCalendar.visible_notes` |
| Add a summary (choosing its readers, who must be invitees) | Organizer only | `add_meeting_note` |
| Add an attendee | Organizer only | `add_attendee` |
| Accept or decline a proxy request | The named proxy only | `respond_proxy` |
| Report an absence | Yourself only | `POST /absences` in `main.py` |
| Reset demo data | Guests only; refused when signed in, and refused outside the demo area | `POST /dev/reset-demo`, `seed.reset_demo` |
| Connect or sync Google Calendar | Signed-in company people only | `real_people_only` in `main.py` |
| Run reminders | Only the Cloud Scheduler service account (OIDC) | `require_scheduler` in `main.py` |

## Design notes

- **Both sides can act, always.** There is no "whose turn is it" rule. `ownerRole` only decides who is emailed first and who the "decider" is for alerts.
- **Only the organizer changes the meeting itself.** This is a product rule; see [Product rules](product-rules.md).
- **A signed-in person can act only as themselves.** An `X-Person-Id` that differs from the verified identity gives 403.
- **Guests are not authenticated.** In the demo area anyone may act as any demo person. That is intended: it is sample data.

## Related
- [Auth and access](../architecture/auth-and-access.md)
- [Actions](actions.md)
- [Privacy rule](../architecture/privacy-rule.md)
