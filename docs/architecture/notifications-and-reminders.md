---
type: Architecture Component
title: Notifications, history and reminders
description: Every email the app would send and its trigger, the in-memory outbox, the activity history log, and the hourly reminder job (proxy reminders, under-24-hour organizer alert).
resource: ../../backend/app/notify.py
tags: [notifications, email, reminders, history, scheduler]
sources:
  - resource: ../../backend/app/notify.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/main.py
  - resource: ../../backend/config/settings.toml
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Notifications, history and reminders

## The outbox (`app/notify.py`)

**No real email is sent.** `send_email(to, subject, body, now)` appends `{to, subject, body, at}` to the in-memory `OUTBOX` and prints it to the console. The web app's **Emails** drawer reads `GET /dev/outbox`:
- signed-in callers see only mail to their own address;
- guests see mail to demo people.

The outbox is cleared on seeding and lost on restart. Calendar invitations and updates are sent by **Google Calendar itself** (`sendUpdates=all`), not by the app.

## Every email and its trigger

| Trigger | To | Subject (shortened) | Code |
|---|---|---|---|
| Absence saved and ≥1 card created | Absent person | "You're out {when}: N meetings need a decision" | `_scan` |
| **Sudden** absence | Each organizer-side decider | "{name} is out suddenly: meetings you organize are affected" | `_scan` |
| Meeting scheduled, added or synced while a key person is out | Organizer (one email for all absentees) | "You scheduled '{title}' while X is out" | `_scan_event` |
| "I'll attend" | Organizer | "FYI: X will still attend '{title}'" | `apply_action` |
| Proxy asked | Proxy | "Can you cover '{title}' for X?" (with the note) | `apply_action` |
| Outside proxy added to the invite | Organizer, unless the organizer asked | "X was added to '{title}' as a proxy for Y" | `_add_proxy_to_meeting` |
| A non-organizer chooses reschedule or cancel | Organizer | "X suggests you reschedule/cancel '{title}'" | `apply_action` |
| A decision made by the other side is changed | Previous decider | "X changed the decision for '{title}'" | `apply_action` |
| An accepted proxy is replaced | That proxy | "You no longer need to cover '{title}'" | `_withdraw_requests` |
| Proxy declines | Absent person and organizer | "X declined to cover '{title}'" | `respond_proxy` |
| Reminder job: silent proxy | Proxy and organizer | "Reminder: the request to cover '{title}' is still unanswered" | `run_reminders` |
| Reminder job: unresolved and under 24 h | Decider (one per meeting) | "Unresolved: '{title}' starts within 24 hours and X is out" | `run_reminders` |

**Planned leave sends organizers no email at creation.** They see the cards in Organizer Mode, and get the under-24-hour alert only if nobody acts. `organizerAlerted` prevents repeat alerts.

## Reminder job (`Service.run_reminders`)

Called by `POST /jobs/run-reminders`, company area only, OIDC-protected (see [Auth and access](auth-and-access.md)). Cloud Scheduler calls it hourly (`0 * * * *`, Asia/Kolkata). It is safe to run more often. It **never acts**; it only reminds.

1. **Proxy reminders.** For each pending request with `remindersSent < [reminders] proxy_max_reminders` (3) whose meeting has not passed: email the proxy and the organizer, and increment the count. At most one reminder per request per run.
2. **Under-24-hour alert.** Key-meeting cards in the attention set with `organizerAlerted = false` that start within `[reminders] organizer_alert_hours` (24) are grouped by (meeting, decider). Each group gets one email, and the cards are marked alerted.

It returns `{"reminders_sent": n}`. **Not built yet** (RESERVED settings):
- milestone digests at `[168, 72, 24, 4, 2]` hours before;
- `recipients`;
- `send_as_digest`;
- the leaver prompt cadence (a TODO in the code).

## History (activity log)

`Service._log` writes a `HistoryEvent` with:
- `detail`: a technical record;
- `text`: a plain sentence for the card's "Activity" in Past.

Types:
- `item_created`
- `meeting_scheduled` (itemId `"-"`)
- `ai_raised`
- `action_chosen`
- `proxy_note`
- `proxy_added_to_meeting`
- `proxy_response`
- `calendar_event_cancelled`

`GET /history` returns entries from the last `[visibility] history_days` (30) where the caller is the actor, or the card is theirs as the absent person or organizer.

## Related
- [Reminder job runbook](../operations/reminder-job.md)
- [Proxy](../concepts/proxy.md)
- [Absence](../concepts/absence.md)
