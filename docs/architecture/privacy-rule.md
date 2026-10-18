---
type: Policy
title: Privacy rule (per-viewer summaries)
description: A person's recommendation, AI prompt and handover draft are built only from meeting summaries that person can open; how the filter works and every place it is applied.
resource: ../../backend/app/calendar.py
tags: [privacy, security, policy, ai, load-bearing]
sources:
  - resource: ../../backend/app/calendar.py
  - resource: ../../backend/agents/orchestrator.py
  - resource: ../../backend/agents/adk_advisor.py
  - resource: ../../backend/app/service.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Privacy rule (per-viewer summaries)

> **A person's recommendation is built only from meeting summaries that person can open.** Nothing from a summary ever reaches someone who could not open it. A missing summary never blocks a recommendation; it only lowers confidence.

This rule is **load-bearing** and deliberately **not configurable** (see [Product rules](../concepts/product-rules.md)).

## The filter

`visible_notes(event, viewer_id)` in `app/calendar.py`. `SimCalendar` and `FirestoreCalendar` behave the same:
- the **organizer** sees all of the meeting's notes;
- anyone else sees only notes whose `sharedWith` contains their id.

The organizer chooses `sharedWith` when adding a summary. It must be a subset of the invitees (`Service.add_meeting_note`). Imported Meet transcripts follow the same rule.

## Where it is applied

| Place | How |
|---|---|
| Recommendation | `orchestrator.analyze` filters **first**. The rules, the single-call prompt and the agent only ever see `visible_notes(event, viewer)` |
| Per-viewer cards | `Service._view` recomputes `ai` for each viewer. The cache key includes the `(docId, modifiedAt)` of the summaries *that viewer* can see, so two viewers with the same access share a result and different access gives different results |
| Card classification | `_create_item` judges the shared kind (routine or not) from the **absent person's** view, so nothing is concluded from documents they cannot open |
| ADK agent | The tools are bound to one viewer's notes. There is no tool to read other meetings or documents, however the agent asks |
| Handover brief | Only the **intersection** of what the sender and the proxy can open (`_draft_notes`). `noteFromAi` sends are re-checked against the proxy |
| Proxy email | Says only whether the proxy can open the notes ("opens with your own access") |
| Reading notes and agenda | `GET /items/{id}/notes` and `/agenda`: invitees only; notes further filtered by `sharedWith` |
| AI prompt size | The AI sees the invitee **count** and at most 20 likely candidates, never the whole audience |

## Example from the seed

- **Design Review** (organized by Meena) has a summary shared only with Dev. Priya is out, but she cannot open it, so her recommendation is built without it, at lower confidence.
- **Release Readiness** notes are shared only with Kiran and Dev.

The test `each_viewer_gets_a_recommendation_from_what_they_can_open` checks this.

## Related
- [Handover brief](../concepts/handover-brief.md)
- [ADK advisor](adk-advisor.md)
- [Analysis cache](analysis-cache.md)
