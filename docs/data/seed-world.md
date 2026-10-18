---
type: Dataset
title: The demo world (seed/seed.json)
description: The sample company used by the demo area; 26 people and their org chart, 35 meetings with summaries, 5 current absences and a replayed past week, plus how to move the dates.
resource: ../../backend/seed/seed.json
tags: [dataset, seed, demo, sample-data]
sources:
  - resource: ../../backend/seed/seed.json
  - resource: ../../backend/app/seed.py
  - resource: ../../backend/README.md
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# The demo world (`backend/seed/seed.json`)

The demo area is built from this file:
- **26 people**, one of them a group;
- **35 meetings**: 28 upcoming on 9–27 Nov 2026 and 7 past on 5–8 Oct 2026;
- **5 current absences**;
- a **replayed past week** (`pastWeek`: 4 absences and 7 decisions).

The top-level keys are `people`, `events`, `absences` and `pastWeek`. Emails are `<first>@example.com`. **No real data.**

Times in the file are UTC. The UI shows IST (+5:30), so `04:00Z` displays as 9:30 am IST.

## People and reporting lines

| Id | Name | Title | Department | Manager |
|---|---|---|---|---|
| `p_arjun` | Arjun Rao | Director | Finance Ops | — |
| `p_priya` | Priya Sharma | Senior Manager | Finance Ops | Arjun |
| `p_meena` | Meena Iyer | Senior Analyst | Finance Ops | Arjun |
| `p_dev` | Dev Nair | Team Lead | Finance Ops | Arjun |
| `p_naomi` | Naomi Fischer | Controller | Finance | Arjun |
| `p_kiran` | Kiran Patel | Analyst | Finance Ops | Priya |
| `p_asha` | Asha Menon | Associate Analyst | Finance Ops | Priya (in no meeting: a directory-only outside proxy) |
| `p_rohan` | Rohan Das | Business Analyst | Finance Ops | Dev |
| `p_ishaan` | Ishaan Kapoor | Senior Analyst | Finance Ops | Dev |
| `p_hana` | Hana Sato | Finance Analyst | Finance Ops | Dev |
| `p_vera` | Vera Lopez | Director | Procurement | — |
| `p_sam` | Sam Wilson | Project Manager | Procurement | Vera |
| `p_tara` | Tara Nguyen | Category Manager | Procurement | Vera |
| `p_zoya` | Zoya Khan | Program Manager | Operations | Vera |
| `p_leo` | Leo Martins | Procurement Analyst | Procurement | Sam |
| `p_luis` | Luis Ortega | Procurement Specialist | Procurement | Sam |
| `p_anya` | Anya Petrova | Operations Analyst | Operations | Zoya |
| `p_neha` | Neha Verma | HR Partner | HR | — |
| `p_ben` | Ben Carter | Legal Counsel | Legal | — |
| `p_lena` | Lena Fox | IT Business Partner | IT | — |
| `p_omar` | Omar Haddad | Engineering Manager | IT | Lena |
| `p_maya` | Maya Chen | Solutions Architect | IT | Lena |
| `p_raj` | Raj Iyer | Security Analyst | IT | Omar |
| `p_sofia` | Sofia Rossi | Data Engineer | IT | Omar |
| `p_kofi` | Kofi Mensah | QA Lead | IT | Omar |
| `p_events` | Site Events Team | Events | Communications | — (**group**, `isGroup: true`; organizes site-wide events) |

## Current absences

| Person | Days | Source | Note |
|---|---|---|---|
| Kiran | 9–10 Nov | manual, entered by Priya | `"type": "sudden"`, forced so the "out suddenly" story works on the real clock |
| Priya | 17–19 Nov | calendar_ooo | Planned leave |
| Arjun | 23–25 Nov | calendar_ooo | Where the AI beats the rules |
| Rohan | 25 Nov | manual | Makes "Rohan usually stands in for Arjun" unavailable |
| Lena | 23–27 Nov | calendar_ooo | A week's vacation with a full calendar |

## Upcoming meetings and what each one exercises

| Meeting (id) | When (UTC) | Organizer | What it tests |
|---|---|---|---|
| Daily Stand-up ×5 (`evt_su_12/13/20/21/22`, series `series_standup`) | 9, 10, 17, 18, 19 Nov 04:00 | Dev | Summary: "status updates only… No decisions." Becomes a **team check-in, auto-handled** |
| Release Readiness (`evt_release`) | 9 Nov 09:30 | Sam | Kiran's sudden absence. Notes are shared only with Kiran and Dev: "Kiran owns the go/no-go checklist. Dev backs up Kiran" |
| Sprint Planning (`evt_sprint`) | 17 Nov 05:30 | **Priya** | Priya organizes and is out. Notes are shared with Meena, Dev and Kiran: "Priya approves the sprint scope." Dev **declines** in the demo story |
| Q4 Budget Review (`evt_budget`) | 18 Nov 09:30 | Sam | "Priya owns the final vendor decision and sign-off. Meena to prepare the cost comparison." Becomes a **proxy: Meena** |
| Site-wide Tech Talk (`evt_techtalk`) | 18 Nov 11:30 | Site Events Team (group, `inviteGroup: site-all`) | **Large event**: an org event, auto-handled, no AI (`rules_policy`) |
| Vendor Contract Decision (`evt_vendor`) | 19 Nov 08:30 | Sam | **No summaries**: a proxy from the reporting line (Arjun), at low confidence |
| Design Review (`evt_design`) | 19 Nov 11:00 | Meena | The summary is shared **only with Dev**, so Priya cannot open it (the privacy rule) |
| Finance Leads Stand-up (`evt_leads_su`) | 23 Nov 04:00 | Dev | Routine with summaries |
| Weekly Ops Sync (`evt_opssync`) | 23 Nov 06:00 | Dev | "Arjun signed off the two analyst roles; they cannot be posted without him." The rules say routine sync; **the AI changes the answer** |
| Pricing Committee (`evt_pricing`) | 24 Nov 05:30 | Sam | "Tara… knows them best. Arjun approves any discount above 20%" |
| All-hands: H2 plan (`evt_allhands`) | 24 Nov 09:30 | Sam | Large event, but "**Arjun walks us through** the H2 numbers": he is named, so the AI looks and finds he presents |
| Acme renewal escalation (`evt_acme`) | 25 Nov 08:30 | Sam | "Acme's CFO will only commit… with Arjun on the call": **reschedule** |
| Audit Committee Prep (`evt_audit_prep`) | 25 Nov 05:30 | **Ben** | "Rohan usually stands in for Arjun", and Rohan is out (and not invited): `check_if_out` |
| IT Ops Stand-up ×5 (`series_it_standup`) | 23–27 Nov 04:30 | Omar | Lena's week: routine |
| Payments Outage Postmortem (`evt_postmortem`) | 23 Nov 08:30 | Sam | "Lena owns the escalation… Decision needed" |
| Q1 IT Roadmap Prioritization (`evt_roadmap`) | 24 Nov 05:30 | **Lena** | Lena organizes and decides the priority order |
| Hiring Panel: Senior SRE (`evt_hiring`) | 25 Nov 09:30 | Sam | Agenda only: "Lena is the hiring manager and makes the final call" |
| Architecture Review Board (`evt_archboard`) | 26 Nov 04:30 | Sam | "Lena presents" the migration plan |
| Cloud Vendor Security Review (`evt_vendorsec`) | 26 Nov 10:30 | Sam | "Omar signs off when Lena is away": a named stand-in |
| Sprint Demo & Retro (`evt_retro`) | 27 Nov 09:30 | Sam | "team feedback only. No decisions." |

No seed meeting has optional invitees. 27 of the 35 meetings carry notes.

## The replayed past week (`pastWeek`)

The replay runs with `now = 2026-10-01T09:00Z`, so these meetings were upcoming at the time. Absences: Dev 6–7 Oct, Meena 8 Oct, Priya 5 Oct, Arjun 6 Oct. Recorded decisions:

| Meeting | Absent | Decided by | Decision |
|---|---|---|---|
| Month-end Close Review | Dev | Dev | Proxy Rohan (accepted) |
| Vendor Onboarding Review | Dev | Sam | Rescheduled |
| Release Go/No-Go | Dev | Dev | Go on without |
| Cost Model Walkthrough | Meena | Meena | Proxy Ishaan (accepted) |
| Q3 Vendor Review | Priya | Priya | Proxy Meena (accepted) |
| Finance Leadership Review | Arjun | Vera | Rescheduled |
| Procurement Ops Review | Meena | Vera | Go on without |

These fill the impact band and the Past tab from the first load. See [Reset demo](../flows/reset-demo.md).

## Why these dates, and how to move them

- The demo runs on the **real clock** (Cloud Run ignores `NOW`).
- The upcoming meetings are placed after the evaluation weeks (19 Oct – 6 Nov 2026), so they stay upcoming for the whole evaluation.
- The test `seed_meetings_stay_upcoming_through_the_evaluation_and_kiran_stays_sudden` guards this.
- **To move the sample data later**, add the same whole number of weeks to every date from 11 Oct 2026 onward, in `seed/seed.json` and in the tests, so weekdays stay the same. The past week and older summaries stay in the past.

## Related
- [Demo personas](demo-personas.md)
- [Reset demo flow](../flows/reset-demo.md)
