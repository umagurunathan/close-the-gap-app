---
type: Config Reference
title: settings.toml
description: Every section of config/settings.toml, what each key does, and whether it's wired or reserved.
resource: backend/config/settings.toml
tags: [config, settings, reference]
timestamp: 2026-10-15T00:00:00Z
---

# `config/settings.toml`

Loaded by [`app/settings.py`](../../backend/app/settings.py) into `settings.<section>.<key>`.
Edit, restart the backend, no code change needed. A missing key fails fast at startup rather than
being silently defaulted. Point at a different file with the `SETTINGS_PATH` environment variable.

Rules that must never change by config are in [concepts/product-rules.md](../concepts/product-rules.md),
not here.

## `[reminders]`

| Key | Status | Meaning |
|---|---|---|
| `milestones_hours_before_meeting` | RESERVED | Hours-before-start milestones for the future digest job (Decision 50): `[168, 72, 24, 4, 2]`. |
| `recipients` | RESERVED | Who gets each digest: `["leaver", "organizer"]`. |
| `send_as_digest` | RESERVED | One digest per person per milestone (`true`) vs. one email per meeting. |
| `job_interval_minutes` | RESERVED | How often Cloud Scheduler would run the job (`15`). |
| `proxy_max_reminders` | **WIRED** | How many times a silent proxy is reminded before the organizer decides instead (`3`). |
| `organizer_alert_hours` | **WIRED** | The current under-24-hour organizer alert window; will be replaced by the digest milestone once built (`24`). |

## `[urgency]` — WIRED

| Key | Meaning |
|---|---|
| `soon_hours` | Amber chip: meeting starts within this many hours and still needs action (`72`). |
| `urgent_hours` | Red "act now" chip (`24`). |

## `[absence]` — WIRED

| Key | Meaning |
|---|---|
| `sudden_notice_hours` | Less notice than this → `AbsenceType.sudden` (organizer emailed at once). Otherwise `planned` (`24`). |

## `[visibility]` — WIRED

| Key | Meaning |
|---|---|
| `past_days` | How long a finished meeting stays in the Past tab (`30`). |
| `history_days` | How far back activity-log entries are shown to a person (`30`). |

## `[reschedule]` — WIRED, plain code (no AI)

| Key | Meaning |
|---|---|
| `preferred_window_hours` | Try the same time of day, within ± this many hours, first (`1`). |
| `wider_window_hours` | Then widen to ± this many hours, flagged as "a little off the original time" (`2`). |
| `step_minutes` | Spacing between candidate times (`30`). |
| `max_working_days` | How many working days ahead to search (`7`). |
| `skip_weekends` | `true`. |

See [`app/scheduling.py`](../../backend/app/scheduling.py).

## `[directory]` — WIRED

| Key | Meaning |
|---|---|
| `max_results` | Cap on directory search results when picking a proxy (`20`). |

## `[metrics]` — WIRED

Illustrative, modeled assumptions behind the "minutes saved" metric — replace with real numbers
when confirmed.

| Key | Meaning |
|---|---|
| `minutes_lost_in_failed_meeting` | Per attendee (`6`). |
| `minutes_lost_in_follow_up` | Per attendee (`30`). |

## `[recommendation]` — WIRED, stand-in rule word lists

Used by the rule-based recommender ([`agents/recommender.py`](../../backend/agents/recommender.py));
Gemini reads the meeting itself once live, but these stay useful as hints and as the fallback.

| Key | Meaning |
|---|---|
| `team_checkin_title_words` | Titles suggesting a stand-up/status sync. |
| `decision_words` | Words suggesting a decision is owned in this meeting. |
| `hosting_words` | Words meaning the absent person runs an org-wide event (Decision 48) — host, emcee, speaker, presenter, moderator, organizer, committee, coordinator. |
| `min_proxy_score_for_high_confidence` | Minimum `proxy_ranking` score to call a suggestion "high confidence" (`10`). |

## `[proxy_ranking]` — WIRED, stand-in rule weights

Used by [`agents/proxy_ranker.py`](../../backend/agents/proxy_ranker.py).

| Key | Meaning |
|---|---|
| `named_in_summaries_base` | Base score for being named in previous summaries, plus one point per mention (`10`). |
| `absent_persons_manager` | Bonus for being the absent person's manager (`3`). |
| `peer_same_manager` | Bonus for a peer under the same manager (`2`). |
| `direct_report` | Bonus for a direct report (`2`). |

## `[drafter]` — WIRED, stand-in rules

Used by [`agents/note_drafter.py`](../../backend/agents/note_drafter.py) to draft a handover note.

| Key | Meaning |
|---|---|
| `key_words` | Sentences containing these (plus the absent person's name) are pulled into the draft. |
| `max_bullets` | Cap on bullets in the draft (`5`). |
| `fallback_sentences` | How many sentences to use if nothing matched `key_words` (`2`). |

## `[ai]` — WIRED, Gemini through Vertex AI

| Key | Meaning |
|---|---|
| `enabled` | `false` = rule-based stand-ins decide (no network, used by tests); `true` = Gemini decides. |
| `model` | Gemini model id, e.g. `"gemini-2.5-flash"` (provisional — Decision A8; run `scripts/hello_gemini.py --list`). |
| `location` | Vertex AI serving region; `"global"` is safest for the newest models. |
| `timeout_seconds` | Per-call timeout (`20`). |
| `thinking_budget` | Gemini "thinking" budget; `0` = off (classification task doesn't need it). |
| `analyse_on_creation` | `false` = cards start with the rule-based answer; Gemini is asked the first time a card is viewed, then cached. Keeps startup/absence-creation from waiting on the network. |
| `attempts` | Retry attempts on temporary failures (`3`). |
| `retry_wait_seconds` | Wait between retries, e.g. `[1, 3]`. |
| `analysing_label_max_seconds` | RESERVED (B22, background analysis): how long a card may say "AI analysing…" before falling back to the rule-based label. |
| `fall_back_to_rules` | Whether an unavailable AI falls back to rules (`true`) or raises. |
| `auto_handle_requires` | Minimum confidence to auto-handle a `team_checkin`/`org_event` (`"high"`). |
| `max_confidence_for_proxy_without_summaries` | Confidence cap for a proxy suggestion resting on the reporting line alone, no summaries (`"low"`). |

See [architecture/recommendation-pipeline.md](../architecture/recommendation-pipeline.md) for how
these are actually used.
