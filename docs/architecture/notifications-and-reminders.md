---
type: Architecture Component
title: Notifications, history and reminders
description: Every email the app would send and its trigger, the in-memory outbox, the activity history log, and the hourly reminder job (proxy reminders, milestone digests, the under-24-hour organizer alert and the invitee alert).
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
| **Sudden** absence | The organizer of each affected meeting, except the absent person themselves | "{name} is out suddenly: meetings you organize are affected" | `_scan` |
| Meeting scheduled, added or synced while a key person is out | Organizer (one email for all absentees) | "You scheduled '{title}' while X is out" | `_scan_event` |
| "I'll attend" | Organizer | "FYI: X will still attend '{title}'" | `apply_action` |
| Proxy asked | Proxy | "Can you cover '{title}' for X?" (with the note) | `apply_action` |
| Outside proxy added to the invite | Organizer, unless the organizer asked | "X was added to '{title}' as a proxy for Y" | `_add_proxy_to_meeting` |
| A non-organizer chooses reschedule or cancel | Organizer | "X suggests you reschedule/cancel '{title}'" | `apply_action` |
| A decision made by the other side is changed | Previous decider | "X changed the decision for '{title}'" | `apply_action` |
| An accepted proxy is replaced | That proxy | "You no longer need to cover '{title}'" | `_withdraw_requests` |
| Proxy declines | Absent person and organizer | "X declined to cover '{title}'" | `respond_proxy` |
| Reminder job: silent proxy | Proxy and organizer | "Reminder: the request to cover '{title}' is still unanswered" | `run_reminders` |
| Reminder job: unresolved and under 24 h | The organizer (one per meeting) | "Unresolved: '{title}' starts within 24 hours and X is out" | `run_reminders` |
| Reminder job: milestone (7 d, 3 d, 24 h, 4 h, 2 h before) | The absent person and the organizer, one digest each | "Reminder: N meetings still need a decision" | `_send_milestone_reminders` |
| Reminder job: the organizer **and** another key person are out, 1–2 h before | Every invitee who is not out | "'{title}' starts at {time} IST: the organizer is out" | `_send_invitee_alerts` |

**Planned leave sends organizers no email at creation.** They see the cards in Organizer Mode, and get the milestone digests and the under-24-hour alert only while nobody has decided. `organizerAlerted`, `milestonesSent` and `inviteesAlerted` prevent repeats.

## Reminder job (`Service.run_reminders`)

Called by `POST /jobs/run-reminders`, company area only, OIDC-protected (see [Auth and access](auth-and-access.md)). Cloud Scheduler calls it hourly (`0 * * * *`, Asia/Kolkata). It is safe to run more often. It **never acts**; it only reminds.

1. **Proxy reminders.** For each pending request with `remindersSent < [reminders] proxy_max_reminders` (3) whose meeting has not passed: email the proxy and the organizer, and increment the count. At most one reminder per request per run.
2. **Under-24-hour alert.** Key-meeting cards in the attention set with `organizerAlerted = false` that start within `[reminders] organizer_alert_hours` (24) are grouped by meeting. The organizer gets one email per meeting, and the cards are marked alerted.
3. **Milestone digests** (`_send_milestone_reminders`). When an undecided key-meeting card passes one of `[reminders] milestones_hours_before_meeting` (168, 72, 24, 4 and 2 hours before the start):
   - the `recipients` (the absent person and the organizer) are reminded; with `send_as_digest`, each person gets **one email per run** listing all their meetings, for example "'Q4 Budget Review' starts in 3 days and you are out.";
   - each milestone is sent **once** per card (`milestonesSent`);
   - **no backfill**: a card created after a milestone never gets it, and after missed runs only the latest milestone is sent;
   - the organizer is skipped at the 24-hour milestone, because the alert above already covers it.
4. **Invitee alert** (`_send_invitee_alerts`). Within `[reminders] invitee_alert_hours` (2) of the start, so 1–2 hours before with the hourly job:
   - only when the **organizer is out that day and at least one other key person is out too**, and the meeting was not moved or canceled and no card for it is closed;
   - every invitee who is not out gets one email saying nobody can reschedule or cancel the meeting, so they should agree by email how to proceed;
   - the email names each other person who is out, and an accepted proxy ("X is out; Y has agreed to cover."); someone who chose "go ahead without me" is not listed;
   - sent once per meeting (`inviteesAlerted`). If only the organizer is out, nothing is sent: the key people can run the meeting.

It returns `{"reminders_sent": n}`. The job only reminds; it never decides or changes a meeting.

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
