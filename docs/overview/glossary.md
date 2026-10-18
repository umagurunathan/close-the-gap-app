---
type: Glossary
title: Glossary
description: The words used across the code, the UI and these docs (area, card, absent person, organizer side, proxy, key person, engine, and more) with their exact meaning.
resource: ../../backend/app/models.py
tags: [glossary, terminology]
sources:
  - resource: ../../backend/app/models.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/roles.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Glossary

Code identifiers are in `code`. The UI, the code and the comments sometimes use different words for the same thing. Both are listed here.

| Term | Meaning |
|---|---|
| **Absence** | A person is out for a range of whole days (`Absence`: `start` and `end` dates, inclusive). It is either *planned* or *sudden*. See [Absence](../concepts/absence.md). |
| **Absent person**, **leaver** | The person who is out. In code: `absentPersonId`. `ownerRole = "leaver"` means the absent person owns the card. |
| **Area**, **workspace** | One of two isolated data partitions: **demo** (guests acting as sample people) and **company** (signed-in directory members). Comments say "area"; the config and Firestore say "workspace" (`FIRESTORE_DEMO_WORKSPACE_ID`, `FIRESTORE_WORKSPACE_ID`, `workspaceId`). See [Areas](../concepts/areas.md). |
| **Card**, **item** | One `MeetingItem` per *(affected meeting, absent person)*. The UI says "card"; the API and code say "item" (`/items`). See [Meeting card](../concepts/meeting-card.md). |
| **Meeting**, **event** | A calendar event (`CalEvent`). A card holds a snapshot of it in `EventRef`. |
| **Organizer side** | The meeting's organizer, plus that organizer's manager when the organizer is the absent person on a sudden absence (`_organizer_side`, `organizer_decider`). |
| **Decider** | The person emailed and expected to decide. For a `leaver` card it is the absent person; otherwise it is the organizer side (`_decider`). Both sides may still act. See [Permissions](../concepts/permissions.md). |
| **Key person** | Someone whose absence needs a decision. Normally the organizer and every required invitee. In a **large event**, only the organizer and people with a **hosting role**. See [Key people](../concepts/key-people.md). |
| **Large event** | A meeting sent to a distribution list (`inviteGroup`), or one with more than 35 required invitees. |
| **Hosting role** | The organizer, or someone named in the same sentence as a hosting word (host, speaker, presenter, keynote…). |
| **Optional invitee** | Never triggers anything. A proxy who was not invited is added as an optional invitee. |
| **Proxy** | Someone who attends in the absent person's place. It can be anyone in the directory except groups, the absent person, and people out that day. See [Proxy](../concepts/proxy.md). |
| **Proxy request** | `ProxyRequest`, with status `pending`, `accepted`, `declined` or `withdrawn`. |
| **Handover brief**, **note** | The message sent with a proxy request. It can be drafted by Gemini ("Draft with AI"). See [Handover brief](../concepts/handover-brief.md). |
| **Summary**, **meeting note** | Text from an earlier occurrence of the meeting (`Note`), shared with chosen invitees (`sharedWith`). It is the AI's main evidence, filtered per viewer. See [Privacy rule](../architecture/privacy-rule.md). |
| **Agenda**, **description** | The invite text (`CalEvent.description`), visible to all invitees. It is treated as untrusted input to the AI. |
| **Kind** | `key_meeting` (a person decides), `team_checkin` or `org_event` (both can be auto-handled). See [Meeting kinds](../concepts/meeting-kinds.md). |
| **Action** | One of five: `attend`, `proceed_without`, `proxy`, `reschedule`, `cancel`. See [Actions](../concepts/actions.md). |
| **Status** | Where a card is in its lifecycle. There are 11 values. See [Meeting card](../concepts/meeting-card.md). |
| **Needs action / Settled / No action needed** | The three groups in every tab. They come from `needsAttention` and the `auto_handled` status. |
| **Auto-handled** | A routine card (team check-in or org-wide event) that goes on without the person with no human decision. The AI may move it *up* to a key meeting, never down. |
| **Engine** | Which path produced a card's recommendation: `gemini_adk`, `gemini`, `rules`, `rules_policy`, `rules_fallback`, `rules_override`, `analysing`, `mixed`. See [Recommendation pipeline](../architecture/recommendation-pipeline.md). |
| **Guard**, **layer C** | Plain-code checks on every AI answer (`agents/guard.py`). See [Guard](../architecture/guard.md). |
| **Rules answer** | What simple keyword rules would have said (`AiResult.rulesAnswer`). It is shown as "AI changed the answer" when it differs from the AI's. |
| **Urgency** | `soon` (amber, within 48 h) or `urgent` (red, within 24 h), only while a card needs attention. |
| **Outbox** | The in-memory list of emails the app *would* send (`GET /dev/outbox`). No real email is sent. |
| **Seed**, **demo world** | `backend/seed/seed.json`: the demo people, meetings, absences and a replayed past week. See [Seed world](../data/seed-world.md). |

## Related
- [Product overview](product.md)
- [Data models](../api/data-models.md)
