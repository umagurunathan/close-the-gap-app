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
- Each section is marked **WIRED** (read by the app). Every section is wired today; the word **RESERVED** would mark a setting agreed in the design whose feature is not built yet.

Product rules are **deliberately not here**. See [Product rules](../concepts/product-rules.md). The `[ai]` section has its own page: [AI settings](ai-settings.md).

## Environment overrides

| Env var | Overrides |
|---|---|
| `SETTINGS_PATH` | Which file is loaded |
| `AI_ENABLED` | `[ai] enabled` (`1/true/yes/on`). The tests set `false` |
| `AI_MODEL` | `[ai] model` |
| `STORE_REQUEST_CACHE` | `[store] request_cache` |

## Sections

### `[reminders]` (WIRED; the hourly job, company area only)
| Key | Value | Meaning |
|---|---|---|
| `milestones_hours_before_meeting` | `[168, 72, 24, 4, 2]` | Milestones for an undecided key meeting; each sent once per card, no backfill |
| `recipients` | `["leaver", "organizer"]` | Who gets each milestone digest |
| `send_as_digest` | `true` | One email per person per run, listing all their meetings |
| `job_interval_minutes` | `60` | Documents the Cloud Scheduler interval (`0 * * * *`); the job itself does not read it |
| `proxy_max_reminders` | `3` | Reminders to a silent proxy before the organizer simply decides |
| `organizer_alert_hours` | `24` | Under-24-hour alert for meetings still needing action; the organizer's 24-hour milestone is skipped, so there is no double email |
| `invitee_alert_hours` | `2` | The organizer and another key person are out: invitees who are not out are told once, 1–2 hours before |

### `[input]` (WIRED; checked by the server, and `maxLength` in the web forms via `web/src/limits.js`)
`title_max_chars = 150`, `agenda_max_chars = 3000`, `proxy_note_max_chars = 2000` (room for the longest Draft with AI brief), `summary_max_chars = 5000`. A longer text is refused with "The title is N characters long. Please keep it to 150." The server also refuses a meeting that starts in the past and an absence that is already over.

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
- `[metrics.projection]`: `company_sizes [1000, 10000, 50000]`, `leave_days_per_year 25`, `key_meetings_per_leave_day 1` (senior roles have more), `hourly_cost 50`, `currency "$"`, `min_meetings_measured 5`, and the fallbacks used until enough meetings are measured: `fallback_share_closed_early 0.6`, `fallback_share_went_ahead 0.4`, `fallback_people_per_meeting 6`, `fallback_days_waiting_avoided 2`.

See [Metrics](../architecture/metrics.md).

### `[recommendation]` (WIRED: stand-in rules and hints)
| Key | Value |
|---|---|
| `team_checkin_title_words` | `stand-up`, `standup`, `stand up`, `dsu`, `daily status`, `status check`, `check-in`, `sync` |
| `decision_words` | `decid`, `decision`, `approve`, `owns`, `owner`, `action item`, `to confirm`, `sign off`, `sign-off` |
| `hosting_words` | `host`, `emcee`, `speaker`, `presenter`, `moderator`, `organis`, `organiz`, `committee`, `co-ordinat`, `coordinat`, `keynote`, `guest`, `panel` |
| `large_meeting_required_threshold` | `35` (was 15). More required invitees than this makes a large event |
| `small_meeting_max_people` | `3`. At or below this the organizer is the counterpart, never the proxy. In a one-to-one (two people) the other person is never the proxy, whoever organized it |
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
