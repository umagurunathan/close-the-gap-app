import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { fmtDay, fmtRange, fmtTime, fmtWhen, needAction, plural } from "./format.js";
import { onTabKey } from "./tabKeys.js";
import MorePeople from "./components/MorePeople.jsx";
import MeetingCard from "./components/MeetingCard.jsx";
import OrganizerCard from "./components/OrganizerCard.jsx";
import ProxyCard from "./components/ProxyCard.jsx";
import ScheduleMeeting from "./components/ScheduleMeeting.jsx";
import SettledCard from "./components/SettledCard.jsx";
import MessageBar from "./components/MessageBar.jsx";
import { useAuth } from "./AuthGate.jsx";
import DemoGuide from "./components/DemoGuide.jsx";
import Logo from "./components/Logo.jsx";
import ImpactBand from "./components/ImpactBand.jsx";
import { EmptyState, Icon } from "./components/Icons.jsx";
import Workspace from "./components/Workspace.jsx";
import { AttendeeTile, OrganizerTile, ProxyTile } from "./components/Tiles.jsx";
import { recall, remember } from "./storage.js";
import { applyTheme } from "./themes.js";

const DEFAULT_PERSON = "p_priya";
// A link can open the app as someone, on a tab: ?as=p_sam&tab=organizer (handy for demos and the judges' guide).
const PARAMS = new URLSearchParams(window.location.search);
const TABS = ["attendee", "organizer", "proxy", "past"];
// The demo's eight people, one click each in the judges' bar, with the part they play. Anyone else appears under
// "More…" only while they have something to do (for example, a proxy request waiting for their answer).
const PERSONAS = [["p_priya", "on leave"], ["p_meena", "proxy"], ["p_sam", "organizer"], ["p_arjun", "AI vs rules"],
  ["p_kiran", "out suddenly"], ["p_lena", "on vacation"], ["p_dev", "declines"], ["p_ben", "audit organizer"]];

// The tab a person lands on: the first with something in "Needs action" (Attendee, then Organizer, then
// Proxy Requests); Attendee when nothing needs action.
function naturalTab(c = {}) {
  if (c.attendeeOpen > 0) return "attendee";
  if (c.organizerOpen > 0) return "organizer";
  if (c.proxyOpen > 0) return "proxy";
  return "attendee";
}

// One app for everyone: a guest acts as one of the demo people; after "Sign in with Google" the same
// screens show only that person's own work (the backend picks the area from the sign-in).
// The app lists only meetings affected by someone's absence (a tester looked for a meeting they had just created with
// no conflict). Every message after scheduling or syncing says so.
const ONLY_CONFLICTS = "Only meetings affected by someone's absence are listed here; the rest stay in your calendar.";

function syncMessage(result) {
  const n = result.affectedItems || 0;
  return `Google Calendar synced: ${result.added} added, ${result.updated} updated. `
    + (n ? `${n} ${n === 1 ? "is" : "are"} affected by an absence and listed below. ` : "None is affected by an absence. ")
    + ONLY_CONFLICTS;
}

const SIGNED_IN = "signed-in";   // pickTabFor marker: choose the tab once the signed-in person's /me arrives

export default function App() {
  const { enabled: signInAvailable, ready: authReady, user: firebaseUser, signIn, signOut } = useAuth();
  const signedIn = Boolean(firebaseUser);
  const [people, setPeople] = useState({});
  // Two separate "who": the demo person a guest acts as, and the signed-in person. Kept apart so that signing in or
  // out switches at once, with no request ever sent as the wrong one.
  const [guestId, setGuestId] = useState(PARAMS.get("as") || recall("personId") || DEFAULT_PERSON);
  const [myId, setMyId] = useState("");
  const personId = signedIn ? myId : guestId;
  const [me, setMe] = useState(null);
  const [absences, setAbsences] = useState([]);
  const [attendee, setAttendee] = useState({ needsAction: [], noActionNeeded: { teamCheckins: [], orgEvents: [], rescheduledOrCancelled: [] } });
  const [organizer, setOrganizer] = useState([]);
  const [proxyReqs, setProxyReqs] = useState([]);
  const [pastItems, setPastItems] = useState([]);
  const [pastProxy, setPastProxy] = useState([]);
  const [history, setHistory] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [outbox, setOutbox] = useState([]);
  const [tab, setTab] = useState(TABS.includes(PARAMS.get("tab")) ? PARAMS.get("tab") : "attendee");
  const [calendarStatus, setCalendarStatus] = useState({ configured: false, connected: false });
  const [showEmails, setShowEmails] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [loadedAt, setLoadedAt] = useState(null);         // when the data on screen was loaded ("Updated 10:42 am")
  const [lastResetAt, setLastResetAt] = useState(null);   // when "Reset demo data" last ran (shown to every guest)
  const [absenceIndex, setAbsenceIndex] = useState(0);   // which of the person's absences the banner shows
  useEffect(() => setAbsenceIndex(0), [personId]);
  const swipeFrom = useRef(null);
  const [notice, setNotice] = useState("");
  const [noticeAction, setNoticeAction] = useState(null); // optional button in the confirmation, e.g. "Open Sam's view"
  const [settings, setSettings] = useState(null); // from GET /settings/public
  const autoSyncedCalendarFor = useRef(null);
  const [activeIds, setActiveIds] = useState(null); // people with something to see; null = not loaded yet
  const [showGuide, setShowGuide] = useState(false);
  const [resetting, setResetting] = useState(false);
  // Each working tab has groups ("Needs action", "Settled", …) and a chosen meeting shown in full on the right.
  const [group, setGroup] = useState({ attendee: "needs", organizer: "needs", proxy: "waiting" });
  const [chosen, setChosen] = useState({});
  // Whose view is on screen: "me" (signed in) or a demo person's id. Until it matches the view asked for, the old
  // cards are faded behind a spinner, so a click on a person, Sign in or Sign out shows at once that it's working.
  const [loadedFor, setLoadedFor] = useState(null);
  const [error, setError] = useState("");
  // After switching person, open the tab where they have something to do (set here, applied once /me arrives).
  // On the first load too, unless the address names a tab.
  const pickTabFor = useRef(TABS.includes(PARAMS.get("tab")) ? null : personId);

  useEffect(() => {
    const url = new URL(window.location.href);
    const meetResult = url.searchParams.get("meet");
    const calendarResult = url.searchParams.get("calendar");
    if (meetResult) {
      setNotice(meetResult === "connected"
        ? "Google Meet connected. Link a Meet to a meeting to import its transcript after the call."
        : "Google Meet connection failed. Check OAuth setup and try again.");
      url.searchParams.delete("meet");
      window.history.replaceState({}, "", url);
    }
    if (calendarResult) {
      if (calendarResult === "connected") {
        setNotice("Google Calendar connected. Importing your meetings now.");
      } else {
        setNotice("Google Calendar connection failed. Check OAuth setup and try again.");
      }
      url.searchParams.delete("calendar");
      window.history.replaceState({}, "", url);
    }
  }, []);

  // the colour theme: ?theme=… in the address (to try one), otherwise the config's [ui] theme
  useEffect(() => {
    api("/settings/public").then((s) => { setSettings(s); applyTheme(PARAMS.get("theme") || s.theme); })
      .catch(() => applyTheme(PARAMS.get("theme")));
  }, []);

  // The people of the area you are in: the demo's for a guest, the company's when signed in.
  useEffect(() => {
    if (!authReady) return;
    api("/people")
      .then((list) => setPeople(Object.fromEntries(list.map((p) => [p.id, p]))))
      .catch((e) => setError(e.message));
  }, [authReady, signedIn]);

  // Signing in: show your own work and open the tab where you have something to do. Signing out: back to the demo.
  const wasSignedIn = useRef(false);
  const authEpoch = useRef(0);   // bumped on sign-in and sign-out: answers to older requests are ignored
  useEffect(() => {
    if (!authReady || signedIn === wasSignedIn.current) return;
    wasSignedIn.current = signedIn;
    authEpoch.current += 1;
    setGroup({ attendee: "needs", organizer: "needs", proxy: "waiting" });
    setChosen({});
    setError("");
    setShowEmails(false);   // the open emails belonged to the other view
    pickTabFor.current = signedIn ? SIGNED_IN : guestId;
    if (!signedIn) setMyId("");
  }, [authReady, signedIn, guestId]);

  // `quiet`: the automatic refresh, which must not clear a message the person is reading
  const refresh = useCallback(async (opts) => {
    if (!authReady) return;   // until Firebase says whether someone is signed in
    const epoch = authEpoch.current;
    const current = () => epoch === authEpoch.current;
    try {
      if (!opts?.quiet) setError("");
      const m = await api("/me", { person: guestId });   // signed in: the token decides who you are
      if (!current()) return;
      const activePersonId = signedIn ? m.person.id : guestId;
      if (signedIn) setMyId(m.person.id);
      const [a, att, org, pr, pi, pp, h, met, ob, cal, act, demo] = await Promise.all([
        api("/absences", { person: activePersonId }),
        api("/items?mode=attendee", { person: activePersonId }),
        api("/organizer/meetings", { person: activePersonId }),   // one card per meeting
        api("/proxy-requests", { person: activePersonId }),
        api("/items?mode=past", { person: activePersonId }),
        api("/proxy-requests?past=true", { person: activePersonId }),
        api("/history", { person: activePersonId }),
        api("/metrics"),
        api("/dev/outbox"),   // the backend sends only the emails for your area (signed in: only yours)
        api("/integrations/google-calendar/status", { person: activePersonId }),
        api("/people/active"),   // who has something to do (for the "More…" list)
        signedIn ? Promise.resolve(null) : api("/dev/demo-status").catch(() => null),   // "Demo data last reset: …"
      ]);
      if (!current()) return;   // signed in or out meanwhile: these answers belong to the old view
      setMe(m); setAbsences(a); setAttendee(att); setOrganizer(org); setProxyReqs(pr); setPastItems(pi); setPastProxy(pp);
      setHistory(h); setMetrics(met); setOutbox(ob); setCalendarStatus(cal); setActiveIds(act);
      setLastResetAt(demo?.lastResetAt || null); setLoadedAt(new Date());
      setLoadedFor(signedIn ? "me" : guestId);
      if (pickTabFor.current === (signedIn ? SIGNED_IN : guestId)) {
        pickTabFor.current = null;
        setTab(naturalTab(m?.counts));
      }
    } catch (e) {
      if (!current()) return;
      setLoadedFor(signedIn ? "me" : guestId);   // stop the spinner; the message says what went wrong
      if (e.code === "not_in_directory") {
        await signOut();   // back to the demo, with the reason shown
        setError(e.message);
        return;
      }
      setError(e.message);
    }
  }, [authReady, guestId, signedIn, signOut]);

  useEffect(() => { refresh(); }, [refresh]);

  // Auto-refresh (testers had to reload to see someone else's change): every few seconds while the page is on screen
  // (`[ui] auto_refresh_seconds`), and at once when the person comes back to the tab. It skips a turn while a pop-up
  // is open or someone is typing, so nothing being written is disturbed, and never shows the loading spinner.
  useEffect(() => {
    const seconds = settings?.autoRefreshSeconds ?? 30;
    if (!seconds) return undefined;
    const busy = () => document.querySelector(".modal-backdrop")
      || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    const tick = () => { if (document.visibilityState === "visible" && !busy()) refresh({ quiet: true }); };
    const timer = setInterval(tick, seconds * 1000);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
  }, [settings, refresh]);

  useEffect(() => {
    if (!signedIn || !personId || !calendarStatus.connected || autoSyncedCalendarFor.current === personId) return;
    autoSyncedCalendarFor.current = personId;
    api("/integrations/google-calendar/sync", { method: "POST" }).then(async (result) => {
      setNotice(syncMessage(result));
      await refresh();
    }).catch((e) => {
      autoSyncedCalendarFor.current = null;
      setError(e.message);
    });
  }, [signedIn, personId, calendarStatus.connected, refresh]);

  // While Gemini is still analysing any card on screen, check again every few seconds; stop once all have answered.
  const analysing = [
    ...attendee.needsAction, ...attendee.noActionNeeded.teamCheckins, ...attendee.noActionNeeded.orgEvents,
    ...organizer.flatMap((m) => [m, ...m.absentees]), ...pastItems,
  ].some((c) => c.ai?.engine === "analysing");
  useEffect(() => {
    if (!analysing) return undefined;
    const timer = setTimeout(refresh, (settings?.refreshWhileAnalysingSeconds ?? 4) * 1000);
    return () => clearTimeout(timer);
  }, [analysing, refresh, attendee, organizer, settings]);

  function switchPerson(id) {
    remember("personId", id);
    pickTabFor.current = id;
    setGuestId(id);
    setGroup({ attendee: "needs", organizer: "needs", proxy: "waiting" });
    setChosen({});
  }

  // Demo only: the demo people (everyone in the sample data) and their meetings go back to the start, and the AI's
  // cache is cleared, so every card is analysed again. Real people's data is not touched.
  async function resetDemo() {
    // the demo is shared: say so before resetting it; the time it ran is then shown to everyone
    if (!window.confirm("Reset the demo for everyone? Anyone trying the demo right now will see it start over. "
      + "Real users' data is not touched.")) return;
    setResetting(true);
    setNoticeAction(null);
    setNotice("Resetting the demo data…");
    try {
      await api("/dev/reset-demo", { method: "POST", person: personId });
      setNotice("Demo data reset. The AI is analyzing every card again.");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setResetting(false);
    }
  }

  async function onSignIn() {
    setError("");
    try {
      await signIn();
    } catch (e) {
      // closing the Google window is not an error worth showing
      if (!/popup-closed|cancelled-popup/.test(e.code || "")) setError("Google sign-in didn't complete. Please try again.");
    }
  }

  async function onSignOut() {
    await signOut();
    setNotice("Signed out. You're back in the demo.");
  }

  // Returns when done, so the card can lock its buttons meanwhile (no double answers).
  async function respond(reqId, response) {
    try {
      await api(`/proxy-requests/${reqId}/respond`, { method: "POST", person: personId, body: { response } });
      setNotice(response === "accepted" ? "Thanks, you're covering this meeting." : "Thanks, your answer has been sent.");
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  async function connectCalendar() {
    try {
      const { authorizationUrl } = await api("/integrations/google-calendar/authorize", { person: personId });
      window.location.assign(authorizationUrl);
    } catch (e) {
      setError(e.message);
    }
  }

  async function syncCalendar() {
    try {
      const result = await api("/integrations/google-calendar/sync", { method: "POST", person: personId });
      setNotice(syncMessage(result));
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  const clearError = useCallback(() => setError(""), []);
  const clearNotice = useCallback(() => { setNotice(""); setNoticeAction(null); }, []);
  const closeGuide = useCallback(() => setShowGuide(false), []);
  function openGuide() {
    setShowGuide(true);
  }
  // "↻ Updated 2:20 pm": the page also refreshes by itself; this says when it last did, and refreshes now on a click.
  // It sits at the end of the group row (Needs action · Settled · …), next to the list it describes.
  const updated = loadedAt && (
    <button className="link updated-at" onClick={() => refresh()}
      title="The page refreshes by itself every few seconds. Click to refresh now.">
      ↻ Updated {fmtTime(loadedAt)}
    </button>
  );
  const pick = (t) => ({ group: group[t], onGroup: (g) => setGroup((x) => ({ ...x, [t]: g })),
    selected: chosen[t], onSelect: (k) => setChosen((x) => ({ ...x, [t]: k })), aside: updated });

  const counts = me?.counts || { attendee: 0, organizer: 0, proxyRequests: 0, attendeeOpen: 0, organizerOpen: 0, proxyOpen: 0 };
  // Activity log lines per meeting, shown inside the cards in Past
  const activityFor = (itemId) => history.filter((h) => h.itemId === itemId).sort((a, b) => a.at.localeCompare(b.at));
  const noAction = attendee.noActionNeeded;
  const affectedCount = attendee.needsAction.length + noAction.teamCheckins.length + noAction.orgEvents.length;
  // Attendee Mode's three groups. Needs action: not settled yet. Settled: a person decided (a proxy accepted,
  // "I'll attend", "go on without me", rescheduled or canceled). No action needed: handled automatically (team
  // check-ins, org-wide events); if someone acts on one, it moves to Settled. Each group: soonest first.
  const byStart = (a, b) => a.event.start.localeCompare(b.event.start);
  const allMine = [...attendee.needsAction, ...noAction.teamCheckins, ...noAction.orgEvents,
    ...(noAction.rescheduledOrCancelled || [])].sort(byStart);
  const attNeeds = allMine.filter((i) => i.needsAttention);
  const attSettled = allMine.filter((i) => !i.needsAttention && i.status !== "auto_handled");
  const attNone = allMine.filter((i) => !i.needsAttention && i.status === "auto_handled");
  // Organizer Mode, the same groups as Attendee Mode: Needs action (most urgent first: red, amber, then by date) and
  // Settled (everyone out has a plan, including meetings rescheduled or canceled), soonest first.
  const URGENCY = { urgent: 0, soon: 1 };
  const openMeetings = organizer.filter((m) => m.needsAttention)
    .sort((a, b) => (URGENCY[a.urgency] ?? 2) - (URGENCY[b.urgency] ?? 2) || a.event.start.localeCompare(b.event.start));
  const settledMeetings = organizer.filter((m) => !m.needsAttention).sort(byStart);
  // Proxy requests: waiting for your answer first, then the ones you answered.
  const waitingReqs = proxyReqs.filter((v) => v.request.status === "pending");
  const answeredReqs = proxyReqs.filter((v) => v.request.status !== "pending");
  // The banner shows one absence at a time, soonest first; ‹ › (or a swipe on a phone) pages through the others.
  // Past absences are left out, and the same days saved twice count once.
  const today = settings?.today || new Date().toISOString().slice(0, 10);
  const myAbsences = [...absences].filter((a) => a.end >= today).sort((a, b) => a.start.localeCompare(b.start))
    .filter((a, n, all) => !all.slice(0, n).some((b) => b.start === a.start && b.end === a.end));
  const absPage = Math.min(absenceIndex, Math.max(myAbsences.length - 1, 0));
  const upcomingAbsence = myAbsences[absPage];
  // The judges' "More…" list: people outside the eight pills who have something to do now (and whoever is viewed now)
  const morePeople = Object.values(people)
    .filter((p) => !p.isGroup && !PERSONAS.some(([id]) => id === p.id)
      && ((activeIds || []).includes(p.id) || p.id === personId))
    .sort((a, b) => a.name.localeCompare(b.name));
  const switching = loadedFor !== (signedIn ? "me" : guestId);
  // the person whose data is on screen (while the next one loads, the faded cards still read as the previous person)
  const shownId = switching && loadedFor ? (loadedFor === "me" ? myId || personId : loadedFor) : personId;
  const guestFirst = (people[guestId]?.name || "").split(" ")[0];
  const loadingText = signedIn ? "Loading your meetings…"
    : loadedFor === "me" || !guestFirst ? "Loading the demo…" : `Loading ${guestFirst}'s meetings…`;
  const noGroupRow = tab === "past" || (tab === "attendee" && allMine.length === 0)
    || (tab === "organizer" && organizer.length === 0) || (tab === "proxy" && proxyReqs.length === 0);

  return (
    <>
      {/* keyboard users: the first Tab offers a jump past the controls to the meetings (hidden until focused) */}
      <a className="skip-link" href="#tab-panel">Skip to meetings</a>
      {/* The strip above the product. A guest gets the Demo controls: the guide, Reset demo data, the emails, and the
          demo people to act as. Someone signed in with Google gets only who they are, their emails and Sign out. */}
      {signedIn ? (
        <div className="demo-toolbar" role="region" aria-label="Your account">
          <div className="demo-toolbar-inner">
            <div className="demo-row">
              <span className="signed-in-as">Signed in as <b>{people[personId]?.name || firebaseUser.email}</b></span>
              <div className="demo-tools">
                <button onClick={() => setShowEmails((v) => !v)} aria-pressed={showEmails}
                  title="The emails the app would have sent you (shown here instead of your inbox)">Emails ({outbox.length})</button>
                <button onClick={onSignOut} title="Sign out and go back to the demo">Sign out</button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        // A section of its own, like the banners below: a heading so visitors know everything in it is for
        // trying the demo; the guide at the far right, Reset just before it; the emails at the end of the people row.
        <section className="demo-toolbar demo-panel" aria-labelledby="demo-heading">
          <div className="demo-toolbar-inner">
           <div className="demo-card dark">
            <div className="demo-row">
              <div className="demo-title">
                <h2 id="demo-heading">Demo controls</h2>
                <span className="demo-sub">Explore the app as any of these sample people. No sign-in needed.</span>
              </div>
              <div className="demo-tools">
                {lastResetAt && <span className="demo-sub demo-last-reset">Last reset: {fmtWhen(lastResetAt)}</span>}
                <button onClick={resetDemo} disabled={resetting}
                  title={resetting ? "Resetting the demo data. This takes about a minute."
                    : "Puts the demo people's meetings back to the start, so the AI analyzes every card again. Real users' data is not touched."}>
                  {resetting ? "Resetting…" : "Reset demo data"}
                </button>
                {/* always highlighted: a visitor may have refreshed or missed it the first time */}
                <button onClick={openGuide} className="guide-new">
                  <Icon name="spark" size={14} className="guide-sparkle" />
                  Demo guide<span className="start-here">Start here</span>
                </button>
              </div>
            </div>
            <div className="demo-row demo-people">
            <div className="demo-view-as" role="group" aria-label="View as">
              <span className="demo-view-label">View as</span>
              {PERSONAS.filter(([id]) => people[id]).map(([id, role]) => (
                <button key={id} className="persona" aria-pressed={personId === id} onClick={() => switchPerson(id)}
                  title={`View the app as ${people[id].name} (${role})`}>
                  {switching && personId === id && <span className="spinner small" aria-hidden="true" />}
                  <b>{people[id].name.split(" ")[0]}</b><span>{role}</span>
                </button>
              ))}
              {/* anyone else only while they have something to do (and whoever is viewed now): a pill like the others
                  that opens a short list; it shows the person's name while one of them is viewed */}
              <MorePeople people={morePeople} current={PERSONAS.some(([id]) => id === personId) ? null : personId}
                onPick={switchPerson} />

            </div>
            <div className="demo-tools">
              <button onClick={() => setShowEmails((v) => !v)} aria-pressed={showEmails}
                title="The emails the app would have sent (shown here instead of real inboxes)">Emails ({outbox.length})</button>
            </div>
            </div>
           </div>
          </div>
        </section>
      )}

    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <Logo size={44} />
          <div>
            <h1 className="brand">Close the <span>Gap</span></h1>
            <div className="tagline">Spot the gap early. Keep the meeting going.</div>
          </div>
        </div>
        {/* The header holds only account things: Sign in, or the person's Google Calendar. The product
            actions (Schedule a meeting, Report an absence) sit next to the tabs, above the meetings they create. */}
        <div className="topbar-right">
          {/* Google Calendar belongs to real people only: the demo uses sample meetings, so guests don't see it */}
          {signedIn && (calendarStatus.connected ? (
            <button className="ghost" onClick={syncCalendar}>Sync Google Calendar</button>
          ) : (
            <button className="ghost" onClick={connectCalendar} disabled={!calendarStatus.configured}
              title={calendarStatus.configured ? undefined : "Google Calendar isn't set up yet."}>
              Connect Google Calendar
            </button>
          ))}
          {/* real people sign in here; the demo stays open to everyone */}
          {signInAvailable && !signedIn && (
            <button className="sign-in" onClick={onSignIn} disabled={!authReady}
              title={authReady ? "Sign in to see only your own meetings" : "Checking whether you're signed in…"}>
              Sign in with Google
            </button>
          )}
        </div>
      </header>

      {showGuide && <DemoGuide onClose={closeGuide} />}

      <MessageBar kind="error" text={error} onClose={clearError} />
      <MessageBar kind="success" text={notice} onClose={clearNotice} hideAfter={settings?.messageHideSeconds ?? 6}
        action={noticeAction} />

      <div className={`view ${switching ? "switching" : ""}`} aria-busy={switching}>
      {switching && (
        <div className="view-loading" role="status"><span className="spinner" aria-hidden="true" />{loadingText}</div>
      )}
      {/* The signed-in person's situation and next step, in two lines: the first thing a visitor reads. */}
      {upcomingAbsence && (() => {
        // With one absence: all the person's cards, as before. With several: the cards of meetings on this absence's
        // days. Each meeting has one card, tied to the first absence that covered it, so when absences overlap the
        // card is matched by its date as well (the same rule as the backend: the meeting's date within the absence).
        const several = myAbsences.length > 1;
        const { start: from, end: to } = upcomingAbsence;
        const mine = several
          ? [...attendee.needsAction, ...noAction.teamCheckins, ...noAction.orgEvents]
              .filter((i) => i.absenceId === upcomingAbsence.id
                || (i.event.start.slice(0, 10) >= from && i.event.start.slice(0, 10) <= to))
          : null;
        const open = several ? mine.filter((i) => i.needsAttention).length : counts.attendeeOpen;
        const total = several ? mine.length : affectedCount;
        const firstName = (people[shownId]?.name || "").split(" ")[0];
        const days = upcomingAbsence.start === upcomingAbsence.end
          ? <b>{fmtDay(upcomingAbsence.start)}</b>
          : <b>{fmtRange(upcomingAbsence.start, upcomingAbsence.end)}</b>;
        const go = (step) => setAbsenceIndex(Math.min(Math.max(absPage + step, 0), myAbsences.length - 1));
        return (
          <section className={`you ${open ? "" : "done"}`} aria-label="Your absence"
            onTouchStart={(e) => { swipeFrom.current = e.touches[0].clientX; }}
            onTouchEnd={(e) => {
              const dx = e.changedTouches[0].clientX - (swipeFrom.current ?? e.changedTouches[0].clientX);
              if (several && Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
              swipeFrom.current = null;
            }}>
            <div className="you-ring"><Icon name={open ? "away" : "check"} size={20} /></div>
            <div className="you-text">
              <div className="you-line">
                {firstName ? `${firstName}, you're` : "You're"} out {days}.{" "}
                {open ? (
                  <><span className="you-count">{open === total ? open : `${open} of ${total}`}</span>{" "}
                    affected {total === 1 ? "meeting" : "meetings"} {open === 1 ? "needs" : "need"} you.</>
                ) : total ? "Every affected meeting has a plan." : "None of your meetings is affected."}
              </div>
              {open > 0 && <div className="you-sub">{open === 1 ? "It has" : "Each has"} an AI recommendation below, soonest first.</div>}
              {!open && total > 0 && <div className="you-sub">You can still change any of them below.</div>}
            </div>
            {several && (
              <div className="you-pager" role="group" aria-label="Your absences">
                <button type="button" onClick={() => go(-1)} disabled={absPage === 0} aria-label="Previous absence"
                  title={absPage === 0 ? "This is your first absence." : "Previous absence"}>‹</button>
                <span aria-live="polite">{absPage + 1} of {myAbsences.length}</span>
                <button type="button" onClick={() => go(1)} disabled={absPage === myAbsences.length - 1}
                  aria-label="Next absence"
                  title={absPage === myAbsences.length - 1 ? "This is your last absence." : "Next absence"}>›</button>
              </div>
            )}
          </section>
        );
      })()}

      {/* refreshed whenever the page refreshes (the overall metrics object changes) */}
      <ImpactBand today={settings?.today} tick={metrics} />

      <nav className="tabs">
        <div className="tab-list" role="tablist" aria-label="Views"
          onKeyDown={(e) => onTabKey(e, TABS, tab, setTab, (id) => `tab-${id}`)}>
          {/* the tab name, then only what needs action: amber, or red when one of them starts within 24 hours */}
          {[
            ["attendee", "Attendee Mode", counts.attendeeOpen, attNeeds.some((i) => i.urgency === "urgent")],
            ["organizer", "Organizer Mode", counts.organizerOpen, openMeetings.some((m) => m.urgency === "urgent")],
            ["proxy", "Proxy Requests", counts.proxyOpen, waitingReqs.some((v) => v.item.urgency === "urgent")],
            ["past", "Past", 0, false],
          ].map(([id, text, open, urgent]) => (
            <button key={id} id={`tab-${id}`} role="tab" aria-selected={tab === id} aria-controls="tab-panel"
              tabIndex={tab === id ? 0 : -1} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
              {text}{open > 0 && <span className={`open ${urgent ? "urgent" : ""}`.trim()}>{needAction(open)}</span>}
            </button>
          ))}
        </div>
        {/* things you can add, as one joined pill of equal buttons, apart from the tabs */}
        <div className="tab-actions" role="group" aria-label="Add">
          <button onClick={() => setShowSchedule(true)}><span aria-hidden="true">＋</span> Schedule a meeting</button>
          <button onClick={() => setShowAdd(true)}><Icon name="away" size={15} /> Report an absence</button>
        </div>
      </nav>

      <main id="tab-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={-1}>
        {/* tabs without the group row (Past, or nothing to list) show "Updated" on a line of its own */}
        {noGroupRow && updated && <div className="updated-row">{updated}</div>}
        {tab === "attendee" && (allMine.length === 0 ? (
          <EmptyState title="No gaps">None of your meetings is affected by an absence, so nothing needs your action.</EmptyState>
        ) : (
          <Workspace label="Attendee Mode" {...pick("attendee")} keyOf={(i) => i.id} titleOf={(i) => i?.event.title}
            groups={[
              { id: "needs", label: "Needs action", items: attNeeds, attention: true,
                empty: { title: "All gaps closed", text: "Every affected meeting has a plan. Nothing needs your action. Only meetings affected by someone's absence are listed here." } },
              { id: "settled", label: "Settled", items: attSettled,
                empty: { title: "Nothing settled yet", text: "Meetings move here once a decision is made: a proxy accepts, you choose to attend or go on without you, or the meeting is rescheduled or canceled." } },
              { id: "none", label: "No action needed", items: attNone,
                empty: { title: "Nothing handled automatically", text: "Team check-ins and org-wide events that can go on without you appear here." } },
            ]}
            renderTile={(i) => <AttendeeTile item={i} people={people} me={shownId} />}
            renderDetail={(i) => (i.status === "rescheduled" || i.status === "cancelled"
              ? <SettledCard title={i.event.title} start={i.event.start} originalStart={i.originalStart} status={i.status}
                  decidedBy={i.decidedBy} organizerId={i.event.organizerId} people={people} />
              : <MeetingCard item={i} people={people} me={shownId} role="attendee" refresh={refresh}
                  quiet={i.status === "auto_handled"} />)}
          />
        ))}

        {tab === "organizer" && (organizer.length === 0 ? (
          <EmptyState title="No gaps">None of the meetings you organize is affected by an absence.</EmptyState>
        ) : (
          <Workspace label="Organizer Mode" {...pick("organizer")} keyOf={(m) => m.calendarEventId} titleOf={(m) => m?.event.title}
            groups={[
              { id: "needs", label: "Needs action", items: openMeetings, attention: true,
                empty: { title: "All gaps closed", text: "Every affected meeting you organize has a plan. Nothing needs your action. Only meetings affected by someone's absence are listed here." } },
              { id: "settled", label: "Settled", items: settledMeetings,
                empty: { title: "Nothing settled yet", text: "Meetings move here once everyone who is out has a plan, or the meeting is rescheduled or canceled." } },
            ]}
            renderTile={(m) => <OrganizerTile meeting={m} people={people} />}
            renderDetail={(m) => (m.done
              ? <SettledCard title={m.event.title} start={m.event.start} originalStart={m.absentees[0]?.originalStart}
                  status={m.absentees[0]?.status} decidedBy={m.absentees[0]?.decidedBy} organizerId={m.event.organizerId}
                  people={people} />
              : <OrganizerCard meeting={m} people={people} me={shownId} refresh={refresh} />)}
          />
        ))}

        {tab === "proxy" && (proxyReqs.length === 0 ? (
          <EmptyState title="No pending coverage requests">You'll be notified when a colleague requests you as a proxy.</EmptyState>
        ) : (
          <Workspace label="Proxy Requests" {...pick("proxy")} keyOf={(v) => v.request.id} titleOf={(v) => v?.item.event.title}
            groups={[
              { id: "waiting", label: "Waiting for your answer", items: waitingReqs, attention: true,
                empty: { title: "All answered", text: "You've answered every request to cover a meeting." } },
              { id: "answered", label: "Answered", items: answeredReqs,
                empty: { title: "Nothing answered yet", text: "Requests you accept or decline move here." } },
            ]}
            renderTile={(v) => <ProxyTile view={v} people={people} />}
            renderDetail={(v) => <ProxyCard view={v} people={people} me={shownId} onRespond={respond} />}
          />
        ))}

        {tab === "past" && (
          <div className="single-col">
            <p className="reason">Meetings whose time has passed{settings ? `, kept for ${settings.pastDays} days` : ""}.</p>
            {pastItems.length === 0 && pastProxy.length === 0 && <div className="empty">Nothing in the past yet.</div>}
            {pastItems.length > 0 && <h4 className="group-title">Your meetings</h4>}
            {pastItems.map((i) => (
              <MeetingCard
                key={i.id} item={i} people={people} me={shownId}
                role={i.absentPersonId === shownId ? "attendee" : "organizer"}
                refresh={refresh} readOnly activity={activityFor(i.id)}
              />
            ))}
            {pastProxy.length > 0 && <h4 className="group-title">Meetings you covered</h4>}
            {pastProxy.map((v) => (
              <ProxyCard key={v.request.id} view={v} people={people} me={shownId} activity={activityFor(v.item.id)} />
            ))}
          </div>
        )}
      </main>
      </div>

      {showEmails && (
        <aside className="drawer" aria-label="Emails">
          <header className="guide-head drawer-head">
            <h4>Emails the app sent (demo: shown here instead of real inboxes)</h4>
            <button className="message-close" onClick={() => setShowEmails(false)} aria-label="Close the emails" title="Close">✕</button>
          </header>
          {outbox.length === 0 && <p className="reason">None yet.</p>}
          {[...outbox].reverse().map((m, idx) => (
            <div key={idx} className="mail">
              <div><b>To:</b> {m.to}</div>
              <div><b>{m.subject}</b></div>
              <div className="reason">{m.body}</div>
            </div>
          ))}
        </aside>
      )}

      {showSchedule && (
        <ScheduleMeeting
          today={settings?.today}
          people={people}
          me={personId}
          calendarConnected={calendarStatus.connected}
          onClose={() => setShowSchedule(false)}
          onDone={async (result, when) => {
            setShowSchedule(false);
            const out = result.affected.map((i) => people[i.absentPersonId]?.name.split(" ")[0]).filter(Boolean);
            const who = out.length === 1 ? `${out[0]} is` : `${out.slice(0, -1).join(", ")} and ${out.at(-1)} are`;
            setNoticeAction(null);
            const scheduledWhere = result.calendarProvider === "google"
              ? "Google Calendar updated"
              : "Meeting scheduled";
            setNotice(out.length === 0
              ? `${scheduledWhere} for ${fmtWhen(when)}. Nobody required is out then, so it isn't listed in this app. ${ONLY_CONFLICTS}`
              : `${scheduledWhere} for ${fmtWhen(when)}, but ${who} out that day. It's in your Organizer Mode, ready for a decision.`);
            if (out.length > 0) {
              setTab("organizer");
              setGroup((g) => ({ ...g, organizer: "needs" }));
              setChosen((c) => ({ ...c, organizer: result.eventId }));
            }
            await refresh();
          }}
        />
      )}

      {showAdd && (
        <AddAbsence
          today={settings?.today}
          suddenHours={settings?.suddenNoticeHours}
          people={people}
          me={personId}
          onClose={() => setShowAdd(false)}
          onDone={async (report) => {
            setShowAdd(false);
            const a = report.absence;
            const person = people[a.personId]?.name ?? "";
            const first = person.split(" ")[0];
            const mine = a.personId === personId;
            const span = a.start === a.end ? fmtDay(a.start) : `${fmtDay(a.start)} – ${fmtDay(a.end)}`;
            const n = report.affected;
            const what = n === 0 ? "No meetings are affected."
              : `${n} ${n === 1 ? "meeting is" : "meetings are"} affected${report.needDecision ? `, ${report.needDecision} need${report.needDecision === 1 ? "s" : ""} a decision` : ""}.`;
            setNotice(`Absence saved: ${mine ? "you are" : `${person} is`} out ${span}. ${what}`);
            // reporting someone else: their new cards are in their view, one click away
            setNoticeAction(!mine && n > 0 ? { label: `Open ${first}'s view`, onClick: () => switchPerson(a.personId) } : null);
            await refresh();
          }}
        />
      )}
    </div>
    </>
  );
}

// A date `days` after an ISO date ("2026-10-11" + 14 -> "2026-10-25"), as a plain calendar date.
function addDays(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function AddAbsence({ people, me, onClose, onDone, suddenHours, today }) {
  // Nobody pre-chosen (so the person is picked on purpose); dates default to two weeks from the demo's "today".
  const base = today || "2026-10-11";
  const [form, setForm] = useState({ personId: "", start: addDays(base, 14), end: addDays(base, 15) });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onDone(await api("/absences", { method: "POST", person: me, body: form }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Report an absence</h3>
        <label>Who is out
          <select required value={form.personId} onChange={(e) => setForm({ ...form, personId: e.target.value })}>
            <option value="" disabled>Choose a person…</option>
            {Object.values(people).filter((p) => !p.isGroup).sort((a, b) => a.name.localeCompare(b.name))
              .map((p) => <option key={p.id} value={p.id}>{p.name}{p.id === me ? " (you)" : ""}</option>)}
          </select>
        </label>
        <label>From <input type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></label>
        <label>To <input type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></label>
        <p className="reason">If it starts within {suddenHours ?? 24} hours it is treated as a sudden absence; otherwise it is planned leave.</p>
        {error && <div className="note warn">{error}</div>}
        <div className="actions">
          <button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="link" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
