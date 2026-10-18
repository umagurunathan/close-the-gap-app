---
type: Architecture Component
title: Web app architecture
description: The React 19 + Vite single-page app; entry chain, the one fetch wrapper, the two identities (demo guest vs signed-in), data loading and polling, URL parameters, themes and storage.
resource: ../../web/src/App.jsx
tags: [frontend, react, vite, firebase, architecture]
sources:
  - resource: ../../web/src/App.jsx
  - resource: ../../web/src/api.js
  - resource: ../../web/src/AuthGate.jsx
  - resource: ../../web/src/firebase.js
  - resource: ../../web/src/main.jsx
  - resource: ../../web/src/themes.js
  - resource: ../../web/src/storage.js
  - resource: ../../web/package.json
generated: {by: claude-code/claude-opus-5-5, at: 2026-10-18T00:00:00Z}
timestamp: 2026-10-18T00:00:00Z
---

# Web app architecture (`web/`)

The web app is a single page built with **React 19** and **Vite 7**. It has:
- **no router** and **no state library**: `App.jsx` owns all state;
- **no CSS framework**: one `styles.css`;
- **Firebase** through the modular `@firebase/app` and `@firebase/auth` packages only.

The scripts are `npm run dev` (port 5173), `npm run build` and `npm run preview`. There is no lint or test script.

## Entry chain

`index.html` → `src/main.jsx`: `StrictMode` › `ErrorBoundary` › `AuthGate` › `App`.

- **`ErrorBoundary`** shows "Something went wrong… nothing you saved is lost" with a Reload button.
- **`AuthGate`** reports who is signed in and gives `api.js` a token provider. It **never blocks** the app: with auth off, it is ready immediately.
- **`firebase.js`**: sign-in is on only when `VITE_FIREBASE_AUTH_ENABLED === "true"` and all four Firebase values are present. It uses Google sign-in with `prompt: select_account` in a popup.

## The one fetch wrapper (`src/api.js`)

`api(path, {method, body, person})` does the following:
- Base URL is `VITE_API_URL`, defaulting to `http://localhost:8000`.
- It always sends `Content-Type: application/json`.
- It sends `Authorization: Bearer <id token>` when signed in. It sends **`X-Person-Id` only when there is no token**.
- A network failure becomes "We can't reach the server right now…".
- A non-2xx response throws `Error(detail)` with `.code` attached, for example `not_in_directory`.
- A validation-error array or an empty detail is replaced by a friendly message, with separate wording for 5xx and 4xx.
- There are no retries or timeouts.

## Two identities, kept apart

- `guestId` is the demo person. It comes from `?as=` or the remembered `personId`, and defaults to `p_priya`.
- `myId` is the signed-in person, set from `GET /me`.
- `personId = signedIn ? myId : guestId`.

Keeping the two apart means signing in or out switches at once, and **no request is ever sent as the wrong person**:
- an `authEpoch` counter drops stale responses;
- while `loadedFor` differs from the current identity, the old cards fade and a "Loading …'s meetings…" overlay shows.

## Data loading (`refresh()`)

`refresh()` calls `GET /me`, then fetches these in parallel:

| Endpoint | Feeds |
|---|---|
| `/absences` | Absence banner (pager over several absences) |
| `/items?mode=attendee` | Attendee Mode |
| `/organizer/meetings` | Organizer Mode |
| `/proxy-requests`, `/proxy-requests?past=true` | Proxy Requests, Past ("Meetings you covered") |
| `/items?mode=past` | Past ("Your meetings") |
| `/history` | Past cards' Activity |
| `/metrics` | Impact band tick |
| `/dev/outbox` | Emails drawer |
| `/integrations/google-calendar/status` | Connect / Sync buttons |
| `/people/active` | "More…" people menu |
| `/dev/demo-status` (guests only) | "Last reset: …" |

On first load, `GET /settings/public` provides `pastDays`, `suddenNoticeHours`, `refreshWhileAnalysingSeconds`, `messageHideSeconds`, `autoRefreshSeconds`, `theme` and `today`. `GET /people` provides the people map.

## Refreshing

| Trigger | Rule |
|---|---|
| Auto-refresh | Every `[ui] auto_refresh_seconds` (30), and on returning to the tab. It runs only while the page is visible and not busy: no modal open and no input focused. 0 = off |
| AI analysing | While any card's `ai.engine === "analysing"`, refresh after `[ai] refresh_while_analysing_seconds` (4) |
| Calendar auto-sync | Once per signed-in person after connecting: `POST /integrations/google-calendar/sync` |
| Manual | "↻ Updated {time}" |

## URL parameters

| Parameter | Effect |
|---|---|
| `?as=p_sam` | Open the demo as that person |
| `?tab=attendee\|organizer\|proxy\|past` | Open that tab. Otherwise the first tab with open work is chosen |
| `?theme=purple\|blue\|clear\|google` | Override the theme from `[ui] theme` |
| `?calendar=…`, `?meet=…` | OAuth return flags. Shown as a notice, then removed from the URL |

Open the app at `http://localhost:5173`, not `127.0.0.1`: CORS and the OAuth redirect both name localhost.

## Small modules

- `themes.js`: `applyTheme(name)` sets CSS variables. The themes are purple (default), blue, clear and google, and text colours aim for at least 4.5:1 contrast.
- `format.js`: status and action labels, urgency chips. **All times are in IST at a fixed +5:30**, for example "Tue, 27 Oct · 3:00 pm IST", with `istFields` and `fromIst` for form fields.
- `storage.js`: `remember` and `recall` wrap localStorage in try/catch. Only `personId` is stored.
- `tabKeys.js`: arrow-key, Home and End navigation for tablists.

## Related
- [Frontend UI](frontend-ui.md)
- [Auth and access](auth-and-access.md)
- [Endpoints](../api/endpoints.md)
