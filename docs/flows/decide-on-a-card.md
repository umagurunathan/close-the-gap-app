---
type: Flow
title: "Flow: decide on a card"
description: What happens inside apply_action and apply_meeting_action; permission check, recording what the decider saw, each action's transition, withdrawing proxy requests, history and override emails.
resource: ../../backend/app/service.py
tags: [flow, actions, lifecycle]
sources:
  - resource: ../../backend/app/service.py
  - resource: ../../backend/app/main.py
  - resource: ../../web/src/components/MeetingCard.jsx
  - resource: ../../web/src/components/OrganizerCard.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Flow: decide on a card

`Service.apply_action` is **the single place where a card changes state**. It is called through `POST /items/{id}/action` (`{action, proxyId?, note?, noteFromAi?, start?}`) and `POST /items/{id}/reschedule`. It is also called once per card by `apply_meeting_action` (`POST /meetings/{eventId}/action`).

## `apply_action(item_id, caller, action, proxy_id, note, note_from_ai, start)`

1. **Load and check**:
   - the card must exist (404);
   - it must not be terminal, that is rescheduled or cancelled (400 "can't be changed any more");
   - the caller must be the absent person or the organizer side (403). See [Permissions](../concepts/permissions.md).
2. **Record what the decider saw.** `recommendedWhenDecided` and `aiWhenDecided` are read from the analysis cache for the caller's visible summaries, falling back to the stored `ai`. This **never waits for the AI**. It feeds "recommendations followed" and the read-only Past view.
3. **Apply the action:**

| Action | Transition and effects |
|---|---|
| `attend` | Absent person on a `leaver` card only (otherwise 400). Status becomes `attending`, and the organizer gets an FYI |
| `proceed_without` | Status becomes `proceeding_without` |
| `proxy` | Validate the proxy: a directory individual, not the absent person, not out that day. If `noteFromAi`, the proxy must be able to open the draft's summaries. For a Google event and an outside proxy, add them in Google first. Withdraw earlier requests (an accepted proxy is told). Create the `ProxyRequest` and email the proxy. Add an outside proxy as optional and FYI the organizer. Status becomes `proxy_requested`. See [Proxy](../concepts/proxy.md) |
| `reschedule` / `cancel` by a non-organizer | Status becomes `awaiting_organizer`, and the organizer gets "X suggests you {action}…" |
| `cancel` by the organizer | `_cancel_meeting` (Google delete first, only once), then status `cancelled` |
| `reschedule` by the organizer | Use the picked `start` (validated by `_check_picked_time`) or else `proposed_time`. With no time, status becomes `no_slot_found`. Otherwise `_move_meeting` (Google PATCH first; if Google refuses, nothing changes), and status becomes `rescheduled` with `originalStart` and `rescheduledTo` set |

4. **Clean up.** For `attending`, `proceeding_without`, `cancelled` or `rescheduled`, any open proxy requests are withdrawn **silently**.
5. **Save** `decidedBy = caller` and `updatedAt`.
6. **Log** `action_chosen` with a plain sentence (`_decision_text`). After a proxy request, also log `proxy_note` ("sent with a note (started as an AI draft)" / "without a note").
7. **Override email.** If the previous decider was someone else on the card and the previous status was neither `pending_decision` nor `auto_handled`, they get "X changed the decision for '…'".
8. **Return** the card as the caller sees it (`_view`).

## `apply_meeting_action(event_id, caller, action, start)` (Organizer Mode)

- The cards are this meeting's upcoming **key-meeting** cards. The caller must be on the organizer side of at least one.
- Only `reschedule`, `cancel` and `proceed_without` are allowed. A proxy is chosen per person.
- **`proceed_without`** applies `apply_action` only to undecided cards (`pending_decision`, `proxy_declined`, `no_slot_found`, `awaiting_organizer`). Arranged proxies and "I'll attend" are kept.
- **`cancel`** applies `apply_action(cancel)` to every open card. The Google delete happens only once.
- **`reschedule`** finds one time: the picked `start`, checked against **all** open absentees, or the proposed time.
  - With no time, every card gets `no_slot_found`.
  - Otherwise there is **one** `_move_meeting`. Every open card becomes `rescheduled`, its requests are withdrawn, and it is logged "(organizer) moved the meeting to a time when everyone is back."
- It returns the updated `OrganizerMeeting`.

## Errors the user may see

Plain-language messages, mapped by `guard()` in `main.py`:
- 400 "Please choose who should cover the meeting.";
- 400 "{Name} is out of office that day. Please choose someone else.";
- 400 "Please pick a time in the future." / "{names} is out that day. Please pick another day.";
- 400 "The organizer must sync their Google Calendar before changing this meeting";
- 403 "Only the person who is out or the organizer can do this.";
- 503 for a Google integration failure.

## Related
- [Actions](../concepts/actions.md)
- [Meeting card](../concepts/meeting-card.md)
- [Reschedule search](../architecture/reschedule-search.md)
