---
type: Product Concept
title: Key people and meeting roles
description: Who matters in a meeting; required vs optional invitees, large events, hosting roles, "named in", and the small-meeting counterpart rule, all from app/roles.py.
resource: ../../backend/app/roles.py
tags: [roles, key-person, large-event, rules]
sources:
  - resource: ../../backend/app/roles.py
  - resource: ../../backend/config/settings.toml
  - resource: ../../backend/app/service.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Key people and meeting roles

`app/roles.py` decides **who matters in a meeting**. It is plain code, shared by:
- the absence scan,
- the "meeting scheduled while someone is out" check,
- the reschedule search,
- the AI agents and the guard.

These are **meeting roles**, not user roles. There is no admin or manager role system; see [Permissions](permissions.md).

## Rules

| Function | Rule |
|---|---|
| `required_ids(event)` | Invitees with `optional = false` |
| `is_invited_as_optional(event, pid)` | Only optional on this invite (not the organizer, not required). **Such a person never triggers anything** |
| `is_large_meeting(event)` | Sent to a distribution list (`inviteGroup` set) **or** more than `[recommendation] large_meeting_required_threshold` (35) required invitees |
| `has_hosting_role(event, person, notes)` | The organizer, **or** the person's first name appears in the same sentence as a `hosting_words` entry (`host`, `emcee`, `speaker`, `presenter`, `moderator`, `organis`/`organiz`, `committee`, `coordinat`, `keynote`, `guest`, `panel`), searched in the title, description and the summaries this viewer may read |
| `is_named_in(event, person, notes)` | Whole-word first name, or full name, in the title, description or visible summaries |
| `people_count(event)` | The organizer plus every invitee, required or optional |
| `organizer_is_counterpart(event, absent_id)` | The organizer is not the absent person and the meeting has ≤ `small_meeting_max_people` (3) people. The organizer is then **the other side** of the meeting (a KT *from* Priya *to* Arjun, organized by Arjun) and is never suggested as the absent person's proxy |
| `is_one_to_one(event)` | Exactly two people, the organizer included |
| `counterparts(event, absent_id)` | Who is on the other side and so can't stand in: in a one-to-one, the other person, whoever organized it; in another small meeting, the organizer (unless the organizer is the one who is out) |
| `key_people(event, people)` | Normal meeting: the organizer plus all required invitees. Large event: the organizer plus required invitees with a hosting role |

## Consequences

- **Who gets a card.** An absence scan creates a card for every meeting where the person is the organizer or a required invitee. In a large event, an ordinary attendee still gets a card, but it is a quiet one (`org_event`, auto-handled). Only the organizer and hosts need a decision.
- **Who must be free for a reschedule.** `find_slot` uses `key_people`. See [Reschedule search](../architecture/reschedule-search.md).
- **Who may be a proxy candidate for the AI.** The candidates are invitees and the organizer, minus the absent person, groups, the `counterparts`, and anyone out that day (`candidates_for` in `agents/recommender_ai.py`). A one-to-one therefore has no candidates, and its card recommends reschedule.
- **Distribution lists are never expanded.** A group (`isGroup: true`, for example `p_events`) is never offered as a proxy.

## Related
- [Meeting kinds](meeting-kinds.md)
- [Guard](../architecture/guard.md), rules 7 and 9
- [Settings (`[recommendation]`)](../config/settings-toml.md)
