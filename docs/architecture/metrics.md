---
type: Architecture Component
title: Impact metrics and company-scale projection
description: How the impact band's numbers are computed (meetings with a plan, team hours saved and at risk, decisions kept on schedule, notice, recommendations followed) and the "At company scale" estimate.
resource: ../../backend/app/service.py
tags: [metrics, impact, estimate, kpi]
sources:
  - resource: ../../backend/app/service.py
  - resource: ../../backend/config/settings.toml
  - resource: ../../web/src/components/ImpactBand.jsx
  - resource: ../../web/src/components/CompanyScale.jsx
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Impact metrics and company-scale projection

The **impact band** at the top of the web app shows company-wide numbers from `GET /metrics?start=&end=` (`Service.metrics`). The period buttons are Last week, This week, Coming weeks and All. **At company scale** opens a projection from `GET /metrics/projection` (`Service.projection`).

Every estimate is **labelled as an estimate on screen**, with its formula. All assumptions are in `[metrics]` in `config/settings.toml`.

## Definitions (`Service.metrics`)

Cards are filtered by their meeting's original date (`instanceStart`). Absences are filtered by overlap with the window.

| Metric | Formula |
|---|---|
| `meetingsAffected` | Cards in the window |
| `meetingsWithPlan` | Cards whose status is in `plan_statuses`: `auto_handled`, `proceeding_without`, `attending`, `proxy_accepted`, `rescheduled`, `cancelled` |
| `handledAutomatically` | Planned cards with status `auto_handled` |
| `avgNoticeDays` | Mean of (meeting start − `updatedAt`) in days over planned cards: how early the plan was made |
| `teamHoursSaved` | Σ over planned cards of (people in the meeting, organizer included) × `minutes_saved_per_invitee[status]` ÷ 60 |
| `teamHoursAtRisk` | Σ over upcoming, unplanned key meetings of people × `at_risk_minutes_per_invitee` (5) ÷ 60 |
| `decisionsOnSchedule` | Key meetings that went ahead (`proxy_accepted` or `proceeding_without`) instead of waiting |
| `daysWaitingAvoided` | For those, the days from the meeting to the first weekday after the absence ends |
| `recommendationsFollowedPct` | Of the cards a person decided, the share where `chosenAction == recommendedWhenDecided` |
| `peopleSpared` | People in meetings whose outcome saved time |
| `absencesSpotted` | Absences overlapping the window |

**Minutes saved per person** (`[metrics.minutes_saved_per_invitee]`). These are deliberately conservative (decided 2026-10-16): only a **wasted start** counts, meaning everyone joins, waits and gives up.

| Outcome | Minutes |
|---|---|
| `proxy_accepted`, `rescheduled`, `cancelled` | 5 |
| `proceeding_without`, `attending`, `auto_handled` | 0 (nothing would have gone wrong) |

The seed's **replayed past week** (meetings on 5–8 Oct 2026) gives the tiles real handled examples from the first load. See [Seed world](../data/seed-world.md).

## Company-scale projection (`Service.projection`)

Per company size in `company_sizes` (500, 5 000, 50 000):

```
affected key meetings / year = employees × leave_days_per_year (25) × key_meetings_per_leave_day (2)
hours saved                  = affected × share_closed_early × people_per_meeting × minutes (5) / 60
value                        = hours × hourly_cost (50, currency "$")
decisions on schedule        = affected × share_went_ahead
days of waiting avoided      = decisions on schedule × days_waiting_avoided
```

The rates (`share_closed_early`, `share_went_ahead`, `people_per_meeting`, `days_waiting_avoided`) are **measured** from this app's own key-meeting cards once there are at least `min_meetings_measured` (5) decided ones. Before that the `fallback_*` values are used (0.6, 0.4, 6, 2). The response says which (`measured`, `meetingsMeasured`).

## Related
- [Settings (`[metrics]`)](../config/settings-toml.md)
- [Frontend UI](frontend-ui.md)
