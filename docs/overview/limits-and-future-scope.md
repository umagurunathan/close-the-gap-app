---
type: Product Overview
title: Known limits and future scope
description: What the prototype deliberately does not do yet, checked against the code, and the planned next steps.
resource: ../../README.md
tags: [limits, roadmap, scope]
sources:
  - resource: ../../README.md
  - resource: ../../backend/app/service.py
  - resource: ../../backend/config/settings.toml
  - resource: ../../web/src/components/Summaries.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Known limits and future scope

These are the prototype's honest limits. Each one names the place in the code that confirms it, so a reader can tell a deliberate limit from a bug.

## Limits today

| Limit | Evidence in code |
|---|---|
| **Absences come only from "Report an absence".** An out-of-office block in Google Calendar is not read as an absence; it is simply not imported as a meeting. | `NOT_MEETINGS` in `app/google_calendar.py`; `POST /absences` in `app/main.py` |
| **People report only their own absence.** A manager or delegate cannot report for someone else. | `post_absence` returns 403 when `personId != who` |
| **No real email.** Emails go to the in-memory outbox. | `app/notify.py` |
| **Milestone reminders** (7 days, 3 days, 24 h, 4 h and 2 h before) are designed but not built. Only proxy reminders and the under-24-hour organizer alert exist. | `[reminders]` RESERVED keys; `Service.run_reminders` TODO |
| **Rescheduling only sees meetings the app knows**, not a colleague's full Google Calendar (there is no free/busy query). | `SimCalendar.busy`, `app/scheduling.py` |
| **One proposed time**, not two or three. | `find_slot` returns the first fit |
| **A time the organizer picks is checked for absences only**, not for whether people are busy at that hour. | `Service._check_picked_time` |
| **A meeting moved only in Google Calendar** shows its new time after a sync, but its card is not closed automatically. | `Service.sync_google_events` |
| **All times are shown in IST** (fixed +5:30) for every viewer. The backend computes day boundaries in UTC. | `web/src/format.js`; `absence_type`, `find_slot` |
| **A routine meeting is auto-handled only with evidence.** A stand-up with no summaries stays in Needs action. A card is never moved *down* later. | guard rule 5; `Service._maybe_raise` (only upward) |
| **Meeting summaries are typed by the organizer** ("Summaries & agenda" on a card). | `Service.add_meeting_note` |
| **Google Meet transcript import exists in the backend but is hidden in the app.** | `SHOW_MEET_IMPORT = false` in `web/src/components/Summaries.jsx` |
| **The Google sign-in app is not verified by Google**, so a first-time sign-in shows an "unverified app" notice. | Operational, not in code |
| **The demo's sample meetings have fixed dates** (9–27 Nov 2026). Kiran's absence is forced to `"type": "sudden"`. | `backend/seed/seed.json`; see [Seed world](../data/seed-world.md) |
| **One backend instance.** The AI cache, rate limits and outbox live in that instance's memory. | `Service._analysis_cache`, `app/limits.py`, `app/notify.py`; [Deployment](../operations/deployment.md) |
| **Not designed for phones.** The layout targets office laptops; it works on a phone but is not optimized. | `web/src/styles.css` breakpoints |

## Future scope

- **Reporting for someone else**, by a manager, an admin or a named delegate, with the person told and able to correct it.
- **Absences from existing systems**: HR or leave systems, and Calendar out-of-office entries, each confirmed by the person before any card is created. `AbsenceSource.leave_system` and `calendar_ooo` already exist as enum values.
- **Real email and chat notifications**, with the milestone digest run by Cloud Scheduler.
- **Live calendar updates** (push notifications instead of on-demand sync) and free/busy checks across everyone's calendar.
- **More rescheduling choice**: several proposed times, picked times checked against busy and working hours, per-person time zones, and cards that close themselves when a meeting is moved in Google Calendar.
- **Company scale**:
  - a shared cache such as Memorystore, and several backend instances;
  - indexed per-person queries instead of whole-collection reads;
  - database rules that enforce the areas;
  - one area per customer company;
  - a directory sourced from Google Workspace or HR.
- **Operations**: a least-privilege service account, limits shared across instances, a cost cap on AI calls, monitoring and alerts, Google app verification.
- **Automatic summaries** from earlier occurrences, through one adapter per meeting platform, starting with Meet transcripts (built, hidden). Each summary keeps the platform's own permissions.

## Related
- [Product overview](product.md)
- [Known quirks](../operations/known-quirks.md): smaller code and doc drift found while writing these docs
