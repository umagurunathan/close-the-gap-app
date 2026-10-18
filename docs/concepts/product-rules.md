---
type: Policy
title: Hardcoded product rules
description: The rules that are deliberately not tunable in settings.toml (privacy filter, the AI proposes and a person decides, organizer-only changes, one occurrence, optional invitees, key people, five actions) and where code enforces each.
resource: ../../backend/config/settings.toml
tags: [policy, product-rules, invariants]
sources:
  - resource: ../../backend/config/settings.toml
  - resource: ../../backend/agents/guard.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/calendar.py
  - resource: ../../backend/app/roles.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Hardcoded product rules

The header of `backend/config/settings.toml` lists the rules that are **deliberately not tuning knobs**. They are enforced in code and must not be made configurable. When you change behaviour, check that none of these breaks.

| # | Rule | Enforced in |
|---|---|---|
| 1 | **Privacy filter.** A person's AI reads only the summaries that person can open, and nothing from a summary reaches someone who could not open it | `SimCalendar.visible_notes` / `FirestoreCalendar.visible_notes`; `orchestrator.analyze` (filters first); ADK tools bound to one viewer; `_draft_notes` (sender ∩ proxy). See [Privacy rule](../architecture/privacy-rule.md) |
| 2 | **The AI proposes; a person decides.** The AI returns a fixed form and cannot act. Auto-handling happens only for routine kinds at high confidence, and the AI can only *raise* a card, never hide one | `Recommendation` schema; read-only ADK tools; guard rules 5–8 and 10; `Service._maybe_raise` |
| 3 | **Only the organizer can reschedule or cancel.** Anyone else's choice becomes `awaiting_organizer` | `Service.apply_action`, `apply_meeting_action` |
| 4 | **One occurrence at a time.** A card is about one meeting instance; cancel and reschedule affect only that occurrence | `MeetingItem.event` (`EventRef.instanceStart`); recurrence (`seriesId`) is not used by the rules |
| 5 | **Optional attendees never trigger anything** | `roles.is_invited_as_optional` in `Service._scan`; `_scan_event` uses `required_ids` |
| 6 | **Who counts as a key person**: the organizer plus required attendees (in a large event, only hosts) | `roles.key_people` |
| 7 | **The five actions**: attend, proceed_without, proxy, reschedule, cancel | `models.Action`; guard rule 4 (never recommend `attend`) |

## Further rules enforced in code

- **A missing summary never blocks a recommendation**; it only lowers confidence (guard rule 3).
- **People report only their own absence** (`POST /absences`).
- **The demo and the company area never mix** ([Areas](areas.md)).
- **The AI can never break the app**: agent, then single call, then rules ([Recommendation pipeline](../architecture/recommendation-pipeline.md)).
- **Typed text is data, not instructions** ([Prompt-injection defence](../architecture/prompt-injection-defence.md)).
- **A Google Calendar change happens before the app's own change.** If Google refuses, nothing in the app changes (`_move_meeting`, `_cancel_meeting`).

## Related
- [Settings (settings.toml)](../config/settings-toml.md): the tunable side
- [Guard](../architecture/guard.md)
