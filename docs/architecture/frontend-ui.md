---
type: Architecture Component
title: Web app UI (tabs, cards, panels)
description: What each screen and component shows and which endpoint each user action calls; tabs and groups, MeetingCard, OrganizerCard, ProxyCard, the proxy, reschedule and summaries panels, AI display pieces and accessibility.
resource: ../../web/src/components/MeetingCard.jsx
tags: [frontend, ui, components, accessibility]
sources:
  - resource: ../../web/src/App.jsx
  - resource: ../../web/src/components/Workspace.jsx
  - resource: ../../web/src/components/MeetingCard.jsx
  - resource: ../../web/src/components/OrganizerCard.jsx
  - resource: ../../web/src/components/ProxyCard.jsx
  - resource: ../../web/src/components/ProxyPanel.jsx
  - resource: ../../web/src/components/ReschedulePanel.jsx
  - resource: ../../web/src/components/ScheduleMeeting.jsx
  - resource: ../../web/src/components/Summaries.jsx
  - resource: ../../web/src/components/aiBits.jsx
  - resource: ../../web/src/components/ImpactBand.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Web app UI

## Page layout (top to bottom)

1. **Top strip**:
   - Guests see **Demo controls**: the eight personas to "View as", **More…** (people with work right now, from `/people/active`), **Demo guide**, **Reset demo data** (with a confirm step, `POST /dev/reset-demo`), "Last reset: …", and **Emails (n)**.
   - Signed-in people see "Signed in as …", Emails and Sign out.
2. **Header**: logo and tagline, **Sign in with Google**, and, when signed in, **Connect / Sync Google Calendar**.
3. **Absence banner**: "Priya, you're out 17 – 19 Nov. N affected meetings need you." With several absences there is a pager (‹ 1 of 2 ›, or a swipe on touch devices).
4. **Impact band**: see [Metrics](metrics.md). It can be folded to one line.
5. **Tabs**: **Attendee Mode**, **Organizer Mode**, **Proxy Requests**, **Past**. Each tab has a badge "N need action", red if any card is urgent. On the right are **＋ Schedule a meeting** and **Report an absence**.

**Only meetings affected by someone's absence are listed.** A meeting with no conflict never appears.

## Tabs and groups (`Workspace.jsx`)

Each working tab has three groups: **Needs action / Settled / No action needed**. Proxy Requests uses "Waiting for your answer / Answered" instead.
- From 1000 px wide, tiles are on the left and the selected card's detail on the right.
- Narrower than that, tiles stack and open in place.
- When a card you were viewing moves to another group, a note says '"{title}" moved to Settled' with **Show it** and **Next: …**.

| Tab | Contents | Detail component |
|---|---|---|
| Attendee Mode | My cards as the absent person, sorted by start | `MeetingCard role="attendee"`; `SettledCard` once rescheduled or cancelled |
| Organizer Mode | One card per meeting I organize (or decide) with someone out. Needs action is sorted by urgency, then start | `OrganizerCard`; `SettledCard` when done |
| Proxy Requests | Requests addressed to me | `ProxyCard` with Accept / Decline |
| Past | "Your meetings" (read-only, with Activity) and "Meetings you covered", kept `pastDays` | `MeetingCard readOnly`, `ProxyCard` |

## Cards and the actions they call

| Component | Shows | Actions → endpoint |
|---|---|---|
| `MeetingCard` | Title, time, urgency and status chips, invitees, the AI block, notes such as "Moved to…" or "X declined" | "I'll attend" (leaver only), "Go on without me/them", "Ask {name} to cover" / "Choose a proxy", "Reschedule" / "Ask to reschedule", "Cancel this meeting" / "Ask to cancel", all via `POST /items/{id}/action`. The organizer's reschedule first calls `GET /items/{id}/proposed-time` |
| `OrganizerCard` | One meeting, a row per absent person with their own proxy choice, and a combined recommendation | Per person: the proxy panel. For everyone: Reschedule, Go on without them, Cancel, via `POST /meetings/{eventId}/action` |
| `ProxyCard` | Who asked, for whom, the note, whether the notes are open to you | Accept / Decline via `POST /proxy-requests/{id}/respond` |
| `SettledCard` | Old time struck through, then the new time, or "Canceled"; "{who} (organizer) moved it" | — |

The **recommended action leads** only while the card is still undecided: it is primary, with the ✦ icon and "Recommended:". After someone acts, the action taken leads in green with a tick, and the others follow "or change to:". Auto-handled cards hide their actions behind **Review or change**.

## Panels and dialogs

| Component | Purpose | Endpoints |
|---|---|---|
| `ProxyPanel` | Choose a proxy: invitees ranked with reasons and AI first/second choice, or **search the directory** (people out that day are disabled; not-invited people are marked and added as optional). **Draft with AI**, then edit and **Send** | `GET /items/{id}/proxy-candidates`, `GET /directory?q=&day=`, `GET /items/{id}/note-draft/available`, `POST /items/{id}/note-draft`, `POST /items/{id}/action` |
| `ReschedulePanel` | "Proposed: {when}… Everyone who is out will be back, and every key person is free", or pick a date and time in IST. With no slot it opens in pick mode | `POST /items/{id}/action` or `POST /meetings/{id}/action` with `start` |
| `Summaries` | "Summaries & agenda" for invitees. The organizer adds a summary and picks its readers. The Meet import button is hidden (`SHOW_MEET_IMPORT = false`) | `GET /items/{id}/agenda`, `GET /items/{id}/notes`, `POST /items/{id}/notes` |
| `ScheduleMeeting` | Title, agenda (the AI reads it), date, start in IST, duration, invitees (Required/Optional). If someone is out, the app jumps to Organizer Mode on the new card | `POST /events` |
| Report an absence (in `App.jsx`) | Your own absence only; dates default to today+14 and +15 | `POST /absences` |
| `DemoGuide` | The three-minute story and "Also try" personas | — |
| `CompanyScale` | The company-scale table with formulas | `GET /metrics/projection` |

## AI display pieces (`aiBits.jsx`)

- **`AiSource`**: who wrote the recommendation, for example "Gemini · ADK agent", "Gemini", "Adjusted by rules", "AI analyzing…", "Rule-based · AI unavailable". See the engine table in [Recommendation pipeline](recommendation-pipeline.md).
- **`AgentTrail`**: "The agent: Read past summaries → Listed proxy candidates → Checked who's out → Checked by our rules". When the rules' answer differs: "**AI changed the answer.** Without AI, simple rules would have said: …".
- **`ProxySuggestions`**: "Suggested proxies: A (first choice) · B (second choice)", with declined names marked.
- **`RecommendationDetails`**: recommended by, what the AI read (`ai.sources`), meeting summaries (none / available / used), and the guard's adjustments (`ai.checks`).

## Accessibility

- a visible focus ring;
- "Skip to meetings";
- tabs that work with the arrow keys, Home and End;
- `aria-live` counters;
- text contrast of at least 4.5:1;
- `prefers-reduced-motion` respected;
- **a one-line reason on every disabled button**.

## Related
- [Frontend architecture](frontend-architecture.md)
- [Meeting card](../concepts/meeting-card.md)
- [Demo personas](../data/demo-personas.md)
