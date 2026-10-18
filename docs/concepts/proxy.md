---
type: Product Concept
title: Proxy
description: Someone who attends in the absent person's place; how candidates are ranked, how a request is sent, accepted, declined, replaced or withdrawn, and how outside proxies join the invite.
resource: ../../backend/app/service.py
tags: [proxy, delegation, flow]
sources:
  - resource: ../../backend/app/service.py
  - resource: ../../backend/agents/fallback/candidate_order.py
  - resource: ../../backend/agents/recommender_ai.py
  - resource: ../../web/src/components/ProxyPanel.jsx
  - resource: ../../web/src/components/ProxyCard.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Proxy

A **proxy** attends a meeting in the absent person's place, briefed with a handover note. A proxy is the preferred answer when the absent person owns an item that someone else can carry.

**Covering is always the proxy's choice.** The proxy accepts or declines in **Proxy Requests**.

## Who can be a proxy

| Source | Allowed |
|---|---|
| A person choosing in the panel | **Anyone in the directory**, invited or not, except groups, the absent person, anyone out that day, and, in a one-to-one, the other person (`apply_action` checks all four: "This is a one-to-one with Dev, so Dev can't stand in…") |
| The AI suggesting | Only from `candidates_for`: invitees and the organizer, excluding the absent person, groups, the other side of the meeting (the other person in a one-to-one; the organizer of a small meeting), and people out that day. At most `[ai] max_candidates` (20) are shown to the AI, ranked: named in summaries, then reporting line, then organizer, then the rest |

The AI also names a **second choice** (`backupProxyId`), which is ready if the first declines. Guard rule 1 drops any suggestion that is not a valid, available candidate, and promotes the backup when it is valid.

**A one-to-one has nobody to stand in** (Priya's 1:1 with Dev: Dev can't cover a meeting with himself). The card recommends **reschedule** ("A one-to-one with Dev Nair: nobody else is in it to stand in for Priya…"), the panel's suggestions leave Dev out, the directory search shows him disabled with the reason ("it's a one-to-one with them, so they can't stand in"), and the person can still search the directory for someone else, such as their manager.

## The proxy panel's order (`rank_proxies`)

`agents/fallback/candidate_order.py` gives each candidate a score:

| Signal | Points (`[proxy_ranking]`) |
|---|---|
| Named in the summaries the viewer can read | 10 + 1 per mention |
| The absent person's manager | 3 |
| Peer (same manager) | 2 |
| Direct report | 2 |

Each candidate also gets a plain-words reason, for example "Mentioned in an earlier summary · Priya's peer (same manager)" or "Invited, no other link found". `GET /items/{id}/proxy-candidates` marks each person with the viewer's AI `first` or `second` choice and with `declined`.

## Request lifecycle

1. **Send** (`apply_action(..., proxy, proxyId, note, noteFromAi)`):
   - The card becomes `proxy_requested`.
   - Any earlier pending or accepted request for this card is **withdrawn**. An already-accepted proxy is emailed "You no longer need to cover…".
   - A `ProxyRequest` (`pr_…`) is created, and the proxy is emailed "Can you cover '…' for X?" with the note (at most `[input] proxy_note_max_chars`, 2,000 characters) and a line about whether they can open the summaries.
   - If `noteFromAi` is true, the AI draft's source summaries must be readable by this proxy, or the request is refused.
2. **An outside proxy** (not invited) is added to *this one meeting* as an **optional** attendee, so they never become a key person (`_add_proxy_to_meeting`):
   - For a Google event, the Google invite is updated first.
   - Every card's attendee copy is synced.
   - The organizer gets an FYI, unless the organizer made the request.
3. **Accept** (`respond_proxy`): the request becomes `accepted` and the card `proxy_accepted`. No one else is emailed.
4. **Decline**: the request becomes `declined` and the card `proxy_declined`. The absent person and the organizer are emailed. The card shows "X declined. Second choice: Y" **without asking the AI again**; the decline is a fact (`_declined`).
5. **Replace or withdraw**: choosing someone else, or any non-proxy plan (attend, go on without, reschedule, cancel), withdraws open requests. Withdrawn requests stay visible to the proxy as "No longer needed". A replaced outside proxy stays on the invite; only the cover role ends.
6. **Reminders**: a silent proxy is reminded up to `[reminders] proxy_max_reminders` (3) times by the reminder job. The proxy and the organizer are both emailed. Nothing is changed automatically. See [Notifications and reminders](../architecture/notifications-and-reminders.md).

Answering twice with the same answer is a harmless no-op. Changing an answer after replying is refused ("You've already answered").

## Where the proxy sees it

- **Proxy Requests** tab: "Waiting for your answer" / "Answered". A request stays there until the meeting has passed, then moves to Past ("Meetings you covered").
- `GET /proxy-requests`, `POST /proxy-requests/{id}/respond`.

## Related
- [Handover brief](handover-brief.md)
- [Actions](actions.md)
- [Guard](../architecture/guard.md), rules 1, 2, 3 and 9
