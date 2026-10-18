---
type: Product Overview
title: "Close the Gap: product overview"
description: What Close the Gap does, for whom, and the one idea behind it, finding meetings hit by an absence early and recommending one action each.
resource: ../../README.md
tags: [product, overview, hackathon]
sources:
  - resource: ../../README.md
  - resource: ../../backend/app/service.py
  - resource: ../../backend/config/settings.toml
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Close the Gap

**Tagline:** "Spot the gap early. Keep the meeting going."

Close the Gap keeps meetings productive when someone is out of office. When an absence is known, it finds every meeting the absence affects. For each one it recommends the most efficient way forward:
- go on without the person,
- go on with a briefed **proxy**, or
- only when nothing better exists, reschedule.

**A person always decides; the AI only proposes.**

It was built for the **Google Cloud AI Builder Cup 2026**, in the category **Future of Work & Enterprise Productivity**. The live app is at <https://close-the-gap-2026.web.app>, and you can try it without signing in. The sample data is just there to get you started: the **Report an absence** and **Schedule a meeting** features let you add your own leave and meetings and follow them through the full flow.

## The problem

People going on leave usually tell only their manager and their reports. Colleagues on other teams find out at the last minute. Meetings are cancelled after people have joined, or they run without the decision-maker and need a second meeting.

## What the app does, in both directions

1. **An absence is reported:** Close the Gap scans the absent person's calendar for those days and creates one *card* per affected meeting. See [Report an absence](../flows/report-an-absence.md).
2. **A meeting is scheduled on a day a key person is already out:** the same check runs at once and the organizer is told. See [Schedule a meeting](../flows/schedule-a-meeting.md).

Finding the affected meetings is deliberately **plain code**: an absence plus a calendar gives an exact answer, cheaply, every time. Deciding what to do with each meeting means reading what people wrote (agendas and summaries of earlier occurrences). That part is **Gemini**: an ADK agent on Vertex AI, with checks that follow fixed product rules. See [Recommendation pipeline](../architecture/recommendation-pipeline.md).

## Main capabilities

| Capability | Where to read more |
|---|---|
| One recommendation per meeting, with a reason, a confidence, and what the AI read | [Recommendation pipeline](../architecture/recommendation-pipeline.md) |
| Five actions: attend, go on without, proxy, reschedule, cancel | [Actions](../concepts/actions.md) |
| Both sides can act: the absent person (Attendee Mode) and the organizer (Organizer Mode) | [Permissions](../concepts/permissions.md), [Frontend UI](../architecture/frontend-ui.md) |
| Proxy flow: anyone in the directory, accept or decline, second choice ready | [Proxy](../concepts/proxy.md) |
| AI-drafted handover brief for the proxy | [Handover brief](../concepts/handover-brief.md) |
| Safe reschedule: same time of day, next working days, everyone back | [Reschedule search](../architecture/reschedule-search.md) |
| Routine meetings handled automatically when the AI is highly confident | [Meeting kinds](../concepts/meeting-kinds.md) |
| Privacy: each person's AI reads only what that person may open | [Privacy rule](../architecture/privacy-rule.md) |
| Prompt-injection defence in layers | [Prompt-injection defence](../architecture/prompt-injection-defence.md) |
| Impact band: team time saved, decisions kept on schedule, company-scale projection | [Metrics](../architecture/metrics.md) |
| Real Google Calendar for signed-in company users | [Google integrations](../architecture/google-integrations.md) |

## Two areas in one app

Every visitor lands in the **demo area**, with sample people and no sign-in. Someone who signs in with Google and is in the private company directory works in the **company area** with their own meetings. The two areas never share data. See [Areas](../concepts/areas.md).

## Where the AI makes a difference

Each card shows when **"AI changed the answer"** compared with simple keyword rules:

| The meeting says… | Simple rules | Gemini |
|---|---|---|
| "Weekly Ops Sync"; notes: *"Arjun signed off the two analyst roles; they cannot be posted without him"* | Routine sync, so go on without him | A sign-off depends on him, so it needs a decision |
| *"status updates only, no decisions"* | Sees the word "decisions" | Reads the negation, so routine |
| *"Acme's CFO will only commit to the renewal with Arjun on the call"* | Suggests a proxy | Someone outside insists on him, so reschedule |
| *"Rohan usually stands in for Arjun on audit items"*, while Rohan is out | Cannot connect the facts | Checks that Rohan is out and suggests someone else |
| All-hands where *"Arjun walks us through the H2 numbers"* | No hosting keyword, so ignored | He presents, so it needs a decision |

## Related
- [Glossary](glossary.md)
- [Limits and future scope](limits-and-future-scope.md)
- [System overview](../architecture/system-overview.md)
- [Demo personas](../data/demo-personas.md)
