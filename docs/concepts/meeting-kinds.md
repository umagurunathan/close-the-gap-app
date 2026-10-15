---
type: Concept
title: Meeting kinds
description: key_meeting, team_checkin, and org_event — what each means and how a meeting is classified.
resource: backend/app/models.py
tags: [concepts, itemkind]
timestamp: 2026-10-15T00:00:00Z
---

# Meeting kinds (`ItemKind`)

Every `MeetingItem` is classified into exactly one kind
([backend/app/models.py:36](../../backend/app/models.py)):

| Kind | Meaning | Who decides |
|---|---|---|
| `key_meeting` | A small group where the absence may change the outcome. | A person — this is the only kind that ever shows up as "needs my action". |
| `team_checkin` | Stand-ups and status syncs. The absence changes nothing. | Nobody — auto-handled (`proceed_without`). |
| `org_event` | Town halls, talks, site- or company-wide events sent to a large list. | Nobody, *unless* the absent person organizes or hosts it (see rule 7 below) — then it's a `key_meeting`. |

## How the classification is made

The rule-based stand-in ([`agents/recommender.py`](../../backend/agents/recommender.py)) and the
Gemini-backed version ([`agents/recommender_ai.py`](../../backend/agents/recommender_ai.py))
decide `kind` directly as part of their answer. But the classification is never taken at face
value — [`agents/guard.py`](../../backend/agents/guard.py) enforces two rules that can override it
regardless of which engine produced it:

- **A `team_checkin` needs summaries.** Without visible summaries confirming it's status updates
  only, it reverts to `key_meeting` — a title like "Daily Stand-up" alone is not enough evidence.
- **An org-wide event the absent person runs is a `key_meeting`.** If they're the organizer, or
  named next to a "hosting word" (host, emcee, speaker, presenter, moderator, organizer,
  committee, coordinator — see `[recommendation].hosting_words` in
  [config/settings.md](../config/settings.md)), auto-handling would be wrong: someone may need to
  hand over their role. This is "Decision 48".

Auto-handling (`team_checkin` / `org_event` staying auto-handled rather than becoming a
`key_meeting`) additionally requires confidence at least `[ai].auto_handle_requires` — see
[architecture/recommendation-pipeline.md](../architecture/recommendation-pipeline.md#the-guard-layer-agentsguardpy).

## Where it matters downstream

`Service._create_item` only sets `status = auto_handled` /
`chosenAction = proceed_without` when `kind != key_meeting`
([backend/app/service.py:134](../../backend/app/service.py)). The frontend groups by kind too:
[`Service.attendee_items`](../../backend/app/service.py) splits `team_checkin` and `org_event`
into separate "no action needed" buckets shown collapsed in Attendee Mode
(see [architecture/frontend.md](../architecture/frontend.md#tabs)).
