---
type: Dataset
title: Demo personas and the guided tour
description: The eight demo people in the Demo controls, what each one shows, and the three-minute path through the app for judges and new readers.
resource: ../../web/src/components/DemoGuide.jsx
tags: [demo, personas, tour, judging]
sources:
  - resource: ../../web/src/App.jsx
  - resource: ../../web/src/components/DemoGuide.jsx
  - resource: ../../backend/README.md
  - resource: ../../README.md
  - resource: ../../backend/seed/seed.json
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Demo personas and the guided tour

The demo opens at <https://close-the-gap-2026.web.app>, or locally at `http://localhost:5173`, as **Priya**, with no sign-in. **Demo controls** let you "View as" any of eight people (`PERSONAS` in `App.jsx`). **More…** lists everyone else who has something to do right now. **Demo guide** explains what to try.

You can also open a persona and tab directly with a link: `?as=p_sam&tab=organizer`.

## The eight personas

| Persona | Label | What it shows |
|---|---|---|
| **Priya Sharma** (`p_priya`) | on leave | Planned leave 17–19 Nov: stand-ups auto-handled; **Q4 Budget Review** recommends **Meena** from shared summaries; **Design Review**'s summary is not shared with her (privacy); **Vendor Contract Decision** has no summaries (reporting-line proxy, low confidence); she organizes **Sprint Planning**; an org-wide Tech Talk is handled automatically |
| **Meena Iyer** (`p_meena`) | proxy | Asked to cover. Accept in **Proxy Requests**, and Priya's card moves to Settled |
| **Sam Wilson** (`p_sam`) | organizer | **Organizer Mode**: one card per meeting naming everyone out, with whole-meeting actions (reschedule once for everyone) |
| **Arjun Rao** (`p_arjun`) | AI vs rules | Out 23–25 Nov. **Weekly Ops Sync** shows "AI changed the answer" (a sign-off hidden in a "sync"); Acme (outside customer, so reschedule); the all-hands he presents at; Audit prep (Rohan out, so someone else) |
| **Kiran Patel** (`p_kiran`) | out suddenly | Sudden absence 9–10 Nov: cards are owned by the organizer (Sam), who was **alerted at once**. No "I'll attend" |
| **Lena Fox** (`p_lena`) | on vacation | A week off (23–27 Nov) with a full calendar: routine stand-ups, meetings she organizes, decisions she owns, named stand-ins |
| **Dev Nair** (`p_dev`) | declines | As Priya, ask Dev to cover Sprint Planning; as Dev, **decline**. The card shows the second choice without asking the AI again |
| **Ben Carter** (`p_ben`) | audit organizer | Organizer of **Audit Committee Prep**, outside Arjun's team |

**Neha** (`p_neha`, HR) is unrelated: she has nothing to do. That shows that only meetings affected by an absence are ever listed.

## The three-minute path

1. **Priya**: open **Q4 Budget Review**, choose **Ask Meena to cover**, then **Draft with AI** for a handover brief, edit it, and **send**.
2. **Meena**: in **Proxy Requests**, **Accept**. Priya's card moves to **Settled**.
3. **Arjun**: open **Weekly Ops Sync**. The card shows **AI changed the answer**: simple rules saw a routine sync; Gemini read the summaries and found a sign-off that needs him.

Also try:
- Sam's Organizer Mode;
- Kiran (sudden);
- Lena (a full week);
- Dev (decline);
- **Report an absence** for yourself;
- **Schedule a meeting** on a day someone is out;
- **Emails**, the outbox of what the app would send;
- **Reset demo data**, which restores the start for everyone; it asks first and is rate limited.

## Tips

- The demo runs on **today's real date**. The sample meetings are on 9–27 Nov 2026.
- The page refreshes every 30 s, so changes made by others appear without a reload.
- **Report an absence** is for your own absence only.
- Sign in with Google is only for members of the private company directory. Other accounts are told politely and can keep using the demo.

## Related
- [Seed world](seed-world.md)
- [Product overview](../overview/product.md)
- [Frontend UI](../architecture/frontend-ui.md)
