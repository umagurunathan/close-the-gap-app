---
type: Component
title: Frontend
description: The React + Vite single-page app, its one fetch wrapper, and its four tabs.
resource: web/src/App.jsx
tags: [architecture, frontend, react]
timestamp: 2026-10-15T00:00:00Z
---

# Frontend

Single-page app, no router. [`web/src/App.jsx`](../../web/src/App.jsx) owns all state and polls
the backend via `refresh()`, which fans out to `/me`, `/absences`, `/items` (three modes),
`/proxy-requests` (current and past), `/history`, `/metrics`, and `/dev/outbox` in parallel.

## The one fetch wrapper

[`web/src/api.js`](../../web/src/api.js) is the single place that talks to the backend. Every call
goes through `api(path, { method, body, person })`, which:

- sets `X-Person-Id` from `person` when given (this *is* the simulated sign-in — see
  [data/seed.md](../data/seed.md)),
- JSON-encodes the body,
- throws on any non-2xx response, pulling `detail` out of the FastAPI error body when present.

## Tabs

Four tabs, all driven by the same `/items` family of endpoints:

| Tab | Source endpoint(s) | What it shows |
|---|---|---|
| Attendee Mode | `/items?mode=attendee` | Meetings *I* am the absent person for — split into "needs my action" (`key_meeting`) and "no action needed" (`team_checkin` / `org_event`, auto-handled). |
| Organizer Mode | `/items?mode=organizer` | Meetings I organize where someone else is out. |
| Proxy Requests | `/proxy-requests` (+ `?past=true`) | Requests addressed to me to cover for someone. |
| Past | `/items?mode=past` + `/proxy-requests?past=true` | Finished meetings, read-only, for the last `visibility.past_days` days. |

## Components

- [`components/MeetingCard.jsx`](../../web/src/components/MeetingCard.jsx) — the per-item card:
  recommendation, confidence, engine badge (`gemini` / `rules` / `rules_fallback` /
  `rules_override`), and the action buttons.
- [`components/ProxyCard.jsx`](../../web/src/components/ProxyCard.jsx) — a proxy request card
  with accept/decline.
- [`components/Invitees.jsx`](../../web/src/components/Invitees.jsx) — the invitee list for a
  meeting.
- [`components/ScheduleMeeting.jsx`](../../web/src/components/ScheduleMeeting.jsx) — the "schedule
  a new meeting" form, which exercises the same-day-absence flow (see
  [item-lifecycle.md](item-lifecycle.md#scheduling-into-an-absence)).
- [`format.js`](../../web/src/format.js) — small date/pluralization helpers shared across
  components.

## The person switcher

The top-bar person switcher simulates sign-in by changing the `X-Person-Id` header sent on every
call (persisted to `localStorage`). There is no real authentication anywhere in this app.
