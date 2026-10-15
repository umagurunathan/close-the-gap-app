---
type: Dataset
title: Seed data
description: The demo world — people, events, and absences — built from backend/seed/seed.json.
resource: backend/seed/seed.json
tags: [data, seed, demo, personas]
timestamp: 2026-10-15T00:00:00Z
---

# Seed data (`backend/seed/seed.json`)

Loaded at startup by [`app/seed.py`](../../backend/app/seed.py) (path configurable via
`SEED_PATH`, see [config/env.md](../config/env.md)). As of this writing: **18 people**, **11
calendar events** (one has no notes shared at all; one, `evt_vendor`, has no notes), and **2
seeded absences**. `NOW` is fixed via `.env` to `2026-10-11T09:00:00Z` so the demo state is
deterministic.

## Key personas

| Person | Id | Role | Exercises |
|---|---|---|---|
| **Priya Sharma** | `p_priya` | Senior Manager, reports to Arjun Rao (`p_arjun`); manages Kiran, Asha | Planned leave **Oct 20–22, 2026**. Auto-handled stand-ups, a proxy suggestion drawn from shared summaries, a reporting-line fallback, and an org-wide event. |
| **Kiran Patel** | `p_kiran` | Analyst, reports to Priya | Sudden absence **Oct 12–13, 2026**. Exercises the organizer-alerted path (`ownerRole = "organizer"`, immediate email). |
| **Neha Verma** | `p_neha` | HR Partner, no manager | Unrelated to either absence — nothing to do; a control case. |

The org chart below Arjun Rao (Director) and Vera Lopez (Director) covers two reporting lines:
Priya's team (Kiran, Asha) and Dev Nair's team (Rohan, Ishaan), plus Sam Wilson's procurement team
(Leo Martins) under Vera. `p_events` ("Site Events Team") is the one `isGroup = true` entry — never
offered as a proxy (see [`agents/proxy_ranker.py`](../../backend/agents/proxy_ranker.py) and
[`agents/recommender_ai.py:candidates_for`](../../backend/agents/recommender_ai.py)).

## Events

| Event | Group invite? | Notes shared? |
|---|---|---|
| Daily Stand-up (×4 instances) | No | Yes — exercises `team_checkin` auto-handling |
| Release Readiness | No | Yes |
| Sprint Planning | No | Yes |
| Q4 Budget Review | No | Yes |
| Site-wide Tech Talk: Cloud Cost Optimization | `site-all` | No — exercises `org_event` |
| Vendor Contract Decision | No | No — exercises the "no summaries, fall back to reporting line" path |
| Design Review | No | Yes |

## Simulated sign-in

There's no real authentication (see [architecture/backend.md](../architecture/backend.md)). Any
request to a protected endpoint sends `X-Person-Id: <id>` from this table, and the web app's
person switcher in the top bar does exactly this by changing the header on every call.
