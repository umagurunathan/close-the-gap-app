---
type: Flow
title: "Flow: build and reset the demo world"
description: How the demo area is built from seed.json at start (memory) or by Reset demo data (Firestore), including the replayed past week and the forced sudden absence, and the safety checks around it.
resource: ../../backend/app/seed.py
tags: [flow, demo, seed, reset]
sources:
  - resource: ../../backend/app/seed.py
  - resource: ../../backend/app/main.py
  - resource: ../../backend/seed/seed.json
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Flow: build and reset the demo world

## At startup (`seed.build_service`)

| `STORE` | What happens |
|---|---|
| `memory` | A fresh `InMemoryStore` + `SimCalendar` is built from `seed/seed.json`. Then the past week is replayed (`_replay_past_week`) and the current absences are seeded (`_seed_absences`) |
| `firestore` | The service connects to the demo workspace and **writes nothing**. The demo data is loaded only by Reset demo data, so no other code path can put demo data into the database |

The outbox is cleared afterwards, so seeding emails do not look live. The company area (`build_company_service`) is never seeded from the seed file.

## Reset demo data (`POST /dev/reset-demo` → `seed.reset_demo`)

**Guards:**
- 403 if signed in;
- rate limited to `[limits] reset_demo` (2) per 10 minutes per visitor;
- `PermissionError` if the store's workspace is not the demo workspace.

The web app asks for confirmation first.

**In memory**, the existing `Service` is rebuilt **in place**: the same object, so the running app keeps using it. It gets new data and an empty AI cache. Queued background analyses are cancelled first.

**On Firestore:**
1. Background analysis is cancelled (`wait_for_analysis(cancel=True)`).
2. Everything linked to a demo person is deleted:
   - events from the seed, organized by demo people, or imported from a demo person's calendar;
   - their cards, absences, proxy requests and history;
   - calendar and Meet connections.

   Real (company) people's data is untouched.
3. The seed people (with their demo emails) and events are written again.
4. The service is re-initialised, which empties the AI cache.
5. The past week is replayed and the absences are seeded.
6. The outbox is cleared.
7. `lastResetAt` is saved, in **real** time. Every visitor sees it ("Last reset: …", `GET /dev/demo-status`).

After a reset the AI analyses every card again. That is why the reset is rate limited.

## The replayed past week (`_replay_past_week`)

`pastWeek` in the seed has its own `now` (2026-10-01T09:00Z), four absences and seven recorded actions. The replay works like this:
- the service's clock is set back temporarily;
- `replaying = True`, so no background AI runs;
- each absence is created, each action is applied with `apply_action`, and the proxy accepts where `"accept": true`.

The impact tiles and the Past tab therefore start with real, handled examples instead of zeros.

## Current absences (`_seed_absences`)

Each seed absence is created through `create_absence`, so it runs the normal scan. An absence with `"type": "sudden"` (Kiran) keeps that type even though, on the real clock, it is weeks away. That way the "out suddenly" story still works.

## Related
- [Seed world](../data/seed-world.md)
- [Areas](../concepts/areas.md)
- [Storage](../architecture/storage.md)
