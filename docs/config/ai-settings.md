---
type: Configuration
title: AI settings ([ai] in settings.toml)
description: Every key of the [ai] section; model, region, engine, timeouts, retries, background analysis, auto-handling thresholds and confidence caps, with what each changes.
resource: ../../backend/config/settings.toml
tags: [configuration, ai, gemini, vertex-ai]
sources:
  - resource: ../../backend/config/settings.toml
  - resource: ../../backend/agents/orchestrator.py
  - resource: ../../backend/app/service.py
  - resource: ../../backend/agents/guard.py
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# AI settings (`[ai]`)

Gemini goes through **Vertex AI**, with no API key. On Cloud Run the service account needs `roles/aiplatform.user`. Locally, run `gcloud auth application-default login` once and set `GOOGLE_CLOUD_PROJECT`.

## Model and engine

| Key | Value | Meaning |
|---|---|---|
| `enabled` | `true` | Gemini decides; this is the product. `false` = the rule-based stand-ins decide with no network (the tests). Env `AI_ENABLED` overrides it |
| `model` | `"gemini-2.5-flash"` | "Decided for now": fast in asia-south1, low cost, consistent. Env `AI_MODEL` overrides it |
| `location` | `"asia-south1"` | Measured 2026-10-14 from India: median 0.8 s vs 2.9 s for `global`. `global` is the fallback if a newer model is not offered in Mumbai |
| `engine` | `"adk"` | `adk` = the ADK agent first, then the single call, then the rules. `genai` = skip the agent. The tests use `genai` |
| `temperature` | `0` | The same meeting gets the same answer |
| `thinking_budget` | `0` | Thinking off; this is a short classification. Measure before raising it |

## Time limits and retries

| Key | Value | Meaning |
|---|---|---|
| `adk_timeout_seconds` | `45` | Limit for the agent's whole loop |
| `agent_step_attempts` | `3` | Retries per agent step (inside the ADK client) |
| `timeout_seconds` | `20` | Per single Gemini call |
| `attempts` | `3` | Tries of the single call on temporary errors |
| `retry_wait_seconds` | `[1, 3]` | Waits between tries; the last value is reused |
| `retry_status_codes` | `[429, 500, 502, 503, 504]` | "Try again" codes. Other 4xx are not retried |
| `fall_back_to_rules` | `true` | Show the rules' answer, labelled, when the AI fails |
| `warm_up_on_start` | `true` | One tiny call at startup, so the first real request does not pay for connection setup |

## Background analysis

| Key | Value | Meaning |
|---|---|---|
| `analyse_on_creation` | `false` | Cards start with the rules' answer, so creating an absence never waits |
| `analyse_in_background_on_creation` | `true` | Queue the AI as soon as a card is created (from the absent person's view) |
| `background` | `true` | Answer at once with the rules ("AI analyzing…") and fill in the AI later. `false` = wait for the AI (the tests) |
| `background_workers` | `3` | Cards analysed in parallel. More gives faster pages but more risk of 429 |
| `refresh_while_analysing_seconds` | `4` | How often the web app re-polls while a card is analysing |
| `analysing_label_max_seconds` | `60` | After this a card shows "AI unavailable · rule-based suggestion" instead (was 20) |
| `retry_after_failure_seconds` | `300` | After a failure, wait this long before asking again |

## Classification and confidence

| Key | Value | Meaning |
|---|---|---|
| `ai_may_raise_to_key_meeting` | `true` | The AI may move an auto-handled card *up* to a decision; it never hides one |
| `large_event_ai_when_named` | `true` | In a large event, ask the AI only when the absent person is named |
| `auto_handle_requires` | `"high"` | Guard rule 6: the minimum confidence to auto-handle |
| `max_confidence_for_proxy_without_summaries` | `"low"` | Guard rule 3 |
| `max_confidence_for_proxy_named_in_agenda` | `"medium"` | Guard rule 3, when the agenda names the proxy |
| `max_candidates` | `20` | The AI sees the invitee count and at most this many likely candidates |

## Related
- [Recommendation pipeline](../architecture/recommendation-pipeline.md)
- [Analysis cache](../architecture/analysis-cache.md)
- [Guard](../architecture/guard.md)
- [Settings (other sections)](settings-toml.md)
