---
type: Configuration
title: Tunable settings (config/settings.toml)
description: Every section and key of backend/config/settings.toml except [ai]; what is wired vs reserved, defaults, what each controls, and the environment overrides.
resource: ../../backend/config/settings.toml
tags: [configuration, settings, tuning]
sources:
  - resource: ../../backend/config/settings.toml
  - resource: ../../backend/app/settings.py
  - resource: ../../backend/app/service.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Tunable settings (`backend/config/settings.toml`)

**Edit a number or a word list, restart the backend, and the app follows. No code change is needed.**
- `app/settings.py` loads the file (or `SETTINGS_PATH`) into `settings.<section>.<key>`. A UTF-8 byte-order mark is accepted.
- A **missing key fails when it is accessed**, rather than being silently defaulted.
- Each section is marked **WIRED** (read by the app) or **RESERVED** (agreed in the design, but the feature that reads it is not built).

Product rules are **deliberately not here**. See [Product rules](../concepts/product-rules.md). The `[ai]` section has its own page: [AI settings](ai-settings.md).

## Environment overrides

| Env var | Overrides |
|---|---|
| `SETTINGS_PATH` | Which file is loaded |
| `AI_ENABLED` | `[ai] enabled` (`1/true/yes/on`). The tests set `false` |
| `AI_MODEL` | `[ai] model` |
| `STORE_REQUEST_CACHE` | `[store] request_cache` |

## Sections

### `[reminders]`
| Key | Value | Status | Meaning |
|---|---|---|---|
| `milestones_hours_before_meeting` | `[168, 72, 24, 4, 2]` | RESERVED | Digest milestones; no backfill |
| `recipients` | `["leaver", "organizer"]` | RESERVED | Who gets each digest |
| `send_as_digest` | `true` | RESERVED | One email per person per milestone |
| `job_interval_minutes` | `60` | RESERVED | Matches Cloud Scheduler `0 * * * *` |
| `proxy_max_reminders` | `3` | WIRED | Reminders to a silent proxy before the organizer simply decides |
| `organizer_alert_hours` | `24` | WIRED | Under-24-hour alert for meetings still needing action |

### `[urgency]` (WIRED)
`soon_hours = 48` (amber chip) and `urgent_hours = 24` (red "act now").

### `[absence]` (WIRED)
`sudden_notice_hours = 24`. Less notice than this makes the absence **sudden**, and the organizer is emailed at once.

### `[visibility]` (WIRED)
`past_days = 30` (how long a finished meeting stays in Past) and `history_days = 30` (activity log).

### `[ui]` (WIRED, served by `GET /settings/public`)
| Key | Value | Meaning |
|---|---|---|
| `message_hide_seconds` | `6` | Confirmation messages close after this, twice as long for long text. Errors stay until closed |
| `theme` | `"purple"` | `purple`, `blue`, `clear` or `google` (`web/src/themes.js`). `?theme=` overrides it |
| `auto_refresh_seconds` | `30` | Page refresh interval while visible. Pauses while a form is open. `0` = off |

### `[reschedule]` (WIRED, plain code)
`preferred_window_hours = 1`, `wider_window_hours = 2` (flagged "a little off the original time"), `step_minutes = 30`, `max_working_days = 7`, `skip_weekends = true`. See [Reschedule search](../architecture/reschedule-search.md).

### `[directory]` (WIRED)
`max_results = 20` for proxy search results.

### `[metrics]` (WIRED)
- `plan_statuses = ["auto_handled", "proceeding_without", "attending", "proxy_accepted", "rescheduled", "cancelled"]`
- `at_risk_minutes_per_invitee = 5`
- `[metrics.minutes_saved_per_invitee]`: `proxy_accepted 5`, `rescheduled 5`, `cancelled 5`, `proceeding_without 0`, `attending 0`, `auto_handled 0`. Only a wasted start is counted.
- `[metrics.projection]`: `company_sizes [500, 5000, 50000]`, `leave_days_per_year 25`, `key_meetings_per_leave_day 2`, `hourly_cost 50`, `currency "$"`, `min_meetings_measured 5`, and the fallbacks used until enough meetings are measured: `fallback_share_closed_early 0.6`, `fallback_share_went_ahead 0.4`, `fallback_people_per_meeting 6`, `fallback_days_waiting_avoided 2`.

See [Metrics](../architecture/metrics.md).

### `[recommendation]` (WIRED: stand-in rules and hints)
| Key | Value |
|---|---|
| `team_checkin_title_words` | `stand-up`, `standup`, `stand up`, `dsu`, `daily status`, `status check`, `check-in`, `sync` |
| `decision_words` | `decid`, `decision`, `approve`, `owns`, `owner`, `action item`, `to confirm`, `sign off`, `sign-off` |
| `hosting_words` | `host`, `emcee`, `speaker`, `presenter`, `moderator`, `organis`, `organiz`, `committee`, `co-ordinat`, `coordinat`, `keynote`, `guest`, `panel` |
| `large_meeting_required_threshold` | `35` (was 15). More required invitees than this makes a large event |
| `small_meeting_max_people` | `3`. At or below this the organizer is the counterpart, never the proxy |
| `min_proxy_score_for_high_confidence` | `10` |

### `[proxy_ranking]` (WIRED)
`named_in_summaries_base = 10` (+1 per mention), `absent_persons_manager = 3`, `peer_same_manager = 2`, `direct_report = 2`.

### `[drafter]` (WIRED)
| Key | Value | Used by |
|---|---|---|
| `key_words` | the decision words + `to prepare` | Simple (rule-based) note |
| `max_bullets` | `5` | Simple note |
| `fallback_sentences` | `2` | Simple note |
| `max_key_points` | `5` | Gemini brief |
| `max_open_items` | `4` | Gemini brief |
| `temperature` | `0.2` | Gemini brief: a little variety in wording |

### `[limits]` (WIRED, `app/limits.py`)
`window_minutes = 10`, `draft_with_ai = 10`, `reset_demo = 2`. `0` = no limit. See [Auth and access](../architecture/auth-and-access.md#rate-limits).

### `[store]` (WIRED)
`request_cache = true`. See [Storage](../architecture/storage.md#per-request-read-cache).

## Related
- [AI settings](ai-settings.md)
- [Environment variables](environment-variables.md)
