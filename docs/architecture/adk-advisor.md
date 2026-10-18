---
type: Architecture Component
title: ADK meeting advisor agent
description: The Agent Development Kit agent that decides one meeting with three read-only tools bound to one meeting and one viewer, its run loop, timeouts and how its tool use is checked.
resource: ../../backend/agents/adk_advisor.py
tags: [ai, adk, agent, gemini, tools]
sources:
  - resource: ../../backend/agents/adk_advisor.py
  - resource: ../../backend/agents/recommender_ai.py
  - resource: ../../backend/agents/guard.py
  - resource: ../../backend/config/settings.toml
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# ADK meeting advisor agent

`agents/adk_advisor.py` builds an **ADK `LlmAgent` named `meeting_advisor`**, running Gemini (`[ai] model`, Vertex AI, `[ai] location`). It is the first choice when `[ai] engine = "adk"`, which is the default.

The single-call recommender pastes everything into one prompt. This agent works differently: it gets **tools** and decides for itself what to look at and when to stop. ADK runs the loop: Gemini asks for a tool, ADK runs the Python function, Gemini reads the result, and so on until the final answer. The final answer has the **same `Recommendation` schema**, so the guard and the card do not change.

## Tools (`make_tools`)

All three are **read-only** and **bound to one meeting and one viewer**. There is no tool for other meetings or other people's documents. So privacy is enforced by the code that builds the tools, not by the prompt. The tool docstrings are what ADK shows Gemini, so treat them as a contract.

| Tool | Returns |
|---|---|
| `read_summaries()` | `{summaries: [...], count}`: only the summaries the deciding viewer may open, each wrapped in `<summaries>` |
| `list_proxy_candidates()` | Up to `[ai] max_candidates` people (invitees and organizer, available that day, most likely first), each with `id`, `name`, `title`, `relation` |
| `check_if_out(name_or_id)` | `{found, name, out_on_meeting_day}`, matched on id, full name or first name (groups excluded) |

The instructions (`INSTRUCTIONS + TOOL_GUIDE`) tell the agent to:
- **always** read the summaries when the opening message says some are available;
- **always** list candidates before recommending proxy, reschedule or cancel;
- use `check_if_out` when a summary names a natural stand-in who is not on the list. Example: "Rohan, who usually stands in, is out that day".

## Opening message (`describe_meeting`)

The opening message gives the meeting details the agent always needs, so no tool call is spent on them:
- title, agenda (in `<invite_text>`), date, organizer, group-list flag;
- the invitee count and the person on leave;
- **how many summaries are available** ("read them with read_summaries before you answer").

That last line was added after the agent was found skipping summaries and guessing.

## Run mechanics

- **Client** (`_get_agent_client`): Vertex AI with `timeout_seconds` per call and `HttpRetryOptions(attempts=agent_step_attempts (3), initial_delay=1.0, http_status_codes=retry_status_codes)`. One slow step is retried instead of failing the whole run. A run makes about 4 Gemini calls.
- **One long-lived asyncio loop** in a daemon thread (`adk-agent-loop`) is shared by every run. A new loop per run would fail on the second run with "Event loop is closed", because the shared client keeps its connections tied to the loop that opened them.
- `_run_sync` hands the coroutine to that loop and waits up to `[ai] adk_timeout_seconds` (45 s). After that it raises `TimeoutError`, and the orchestrator falls back to the single call.
- `InMemoryRunner` with the final answer stored under `output_key="recommendation"`. A run with no final answer raises.
- The names of the tools used are recorded in `AiResult.toolsUsed` (excluding ADK's internal `set_model_response`). The card shows them as the agent's steps: "Read past summaries → Listed proxy candidates → Checked by our rules".
- `sources_from_tools` builds "Based on" from what the agent actually looked at. Summaries it never read are removed, and "proxy candidate list" and "out-of-office check" are added when those tools were used.

## Checks specific to the agent ([Guard](guard.md))

- **Rule 11:** summaries were available but `read_summaries` was not called. High confidence becomes medium (or a note is added).
- **Rule 12:** reschedule or cancel without calling `list_proxy_candidates`. High confidence becomes medium (or a note is added).

## Tests

`tests/test_flow.py` replaces `_run_sync` with a fake loop (`_adk_on`), so no network is needed. The tests cover:
- tools see only this meeting and this viewer's summaries;
- the answer records the tools used, and "based on" lists only what was looked at;
- the answer is still checked by the guard;
- a failure falls back to the single call and then to the rules;
- skipping summaries and rescheduling without listing candidates are both flagged.

## Related
- [Recommendation pipeline](recommendation-pipeline.md)
- [Privacy rule](privacy-rule.md)
- [AI settings](../config/ai-settings.md)
