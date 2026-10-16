import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { fmtDay, fmtRange, fmtWhen, needAction, plural } from "./format.js";
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
    pickTabFor.current = signedIn ? SIGNED_IN : guestId;
    if (!signedIn) setMyId("");
  }, [authReady, signedIn, guestId]);

  const refresh = useCallback(async () => {
    if (!authReady) return;   // until Firebase says whether someone is signed in
    const epoch = authEpoch.current;
    const current = () => epoch === authEpoch.current;
    try {
      setError("");
      const m = await api("/me", { person: guestId });   // signed in: the token decides who you are
      if (!current()) return;
      const activePersonId = signedIn ? m.person.id : guestId;
      if (signedIn) setMyId(m.person.id);
      const [a, att, org, pr, pi, pp, h, met, ob, cal, act] = await Promise.all([
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
      ]);
      if (!current()) return;   // signed in or out meanwhile: these answers belong to the old view
      setMe(m); setAbsences(a); setAttendee(att); setOrganizer(org); setProxyReqs(pr); setPastItems(pi); setPastProxy(pp);
      setHistory(h); setMetrics(met); setOutbox(ob); setCalendarStatus(cal); setActiveIds(act);
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

  useEffect(() => {
    if (!signedIn || !personId || !calendarStatus.connected || autoSyncedCalendarFor.current === personId) return;
    autoSyncedCalendarFor.current = personId;
    api("/integrations/google-calendar/sync", { method: "POST" }).then(async (result) => {
      setNotice(`Google Calendar synced: ${result.added} added, ${result.updated} updated, ${result.skipped} skipped.`);
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
    if (!window.confirm("Reset the demo data? The demo people's meetings go back to the start and the AI analyzes "
      + "every card again. Real users' data is not touched.")) return;
    setResetting(true);
    setNoticeAction(null);
    setNotice("Resetting the demo data. This takes about a minute.");
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
      setNotice(`Calendar synced: ${result.added} added, ${result.updated} updated, ${result.skipped} skipped.`);
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
  const pick = (t) => ({ group: group[t], onGroup: (g) => setGroup((x) => ({ ...x, [t]: g })),
    selected: chosen[t], onSelect: (k) => setChosen((x) => ({ ...x, [t]: k })) });

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
  const upcomingAbsence = absences[0];
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

  return (
    <>
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
        <div className="demo-toolbar" role="region" aria-label="Demo controls">
          <div className="demo-toolbar-inner">
            <div className="demo-row">
              <span className="demo-label">Demo controls</span>
              <div className="demo-tools">
                {/* always highlighted (Uma): a visitor may have refreshed or missed it the first time */}
                <button onClick={openGuide} className="guide-new">
                  <Icon name="spark" size={14} className="guide-sparkle" />
                  Demo guide<span className="start-here">Start here</span>
                </button>
                <button onClick={resetDemo} disabled={resetting}
                  title={resetting ? "Resetting the demo data. This takes about a minute."
                    : "Puts the demo people's meetings back to the start, so the AI analyzes every card again. Real users' data is not touched."}>
                  {resetting ? "Resetting…" : "Reset demo data"}
                </button>
                <button onClick={() => setShowEmails((v) => !v)} aria-pressed={showEmails}
                  title="The emails the app would have sent (shown here instead of real inboxes)">Emails ({outbox.length})</button>
              </div>
            </div>
            <div className="demo-view-as" role="group" aria-label="View as">
              <span className="demo-view-label">View as</span>
              {PERSONAS.filter(([id]) => people[id]).map(([id, role]) => (
                <button key={id} className="persona" aria-pressed={personId === id} onClick={() => switchPerson(id)}
                  title={`View the app as ${people[id].name} (${role})`}>
                  {switching && personId === id && <span className="spinner small" aria-hidden="true" />}
                  <b>{people[id].name.split(" ")[0]}</b><span>{role}</span>
                </button>
              ))}
              {/* anyone else only while they have something to do (and whoever is viewed now) */}
              <select aria-label="More people" value={PERSONAS.some(([id]) => id === personId) ? "" : personId}
                disabled={morePeople.length === 0}
                title={morePeople.length === 0 ? "Nobody else has something to do right now." : undefined}
                onChange={(e) => e.target.value && switchPerson(e.target.value)}>
                <option value="">More…</option>
                {morePeople.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          </div>
        </div>
      )}

    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <Logo size={44} />
          <div>
            <div className="brand">Close the <span>Gap</span></div>
            <div className="tagline">Spot the gap early. Keep the meeting going.</div>
          </div>
        </div>
        <div className="topbar-right">
          <button className="primary" onClick={() => setShowSchedule(true)}>Schedule a meeting</button>
          <button onClick={() => setShowAdd(true)}>Report an absence</button>
          {calendarStatus.connected ? (
            <button className="ghost" onClick={syncCalendar}>Sync Google Calendar</button>
          ) : (
            <button className="ghost" onClick={connectCalendar} disabled={!calendarStatus.configured}
              title={calendarStatus.configured ? undefined : signedIn ? "Google Calendar isn't set up yet."
                : "Sign in with Google to connect your own calendar. The demo uses sample meetings."}>
              Connect Google Calendar
            </button>
          )}
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
        const open = counts.attendeeOpen;
        const firstName = (people[shownId]?.name || "").split(" ")[0];
        const days = upcomingAbsence.start === upcomingAbsence.end
          ? <b>{fmtDay(upcomingAbsence.start)}</b>
          : <b>{fmtRange(upcomingAbsence.start, upcomingAbsence.end)}</b>;
        return (
          <section className={`you ${open ? "" : "done"}`} aria-label="Your absence">
            <div className="you-ring"><Icon name={open ? "away" : "check"} size={20} /></div>
            <div className="you-text">
              <div className="you-line">
                {firstName ? `${firstName}, you're` : "You're"} out {days}.{" "}
                {open ? (
                  <><span className="you-count">{open === affectedCount ? open : `${open} of ${affectedCount}`}</span>{" "}
                    affected {open === 1 ? "meeting needs" : "meetings need"} you.</>
                ) : affectedCount ? "Every affected meeting has a plan." : "None of your meetings is affected."}
              </div>
              {open > 0 && <div className="you-sub">{open === 1 ? "It has" : "Each has"} an AI recommendation below, soonest first.</div>}
              {!open && affectedCount > 0 && <div className="you-sub">You can still change any of them below.</div>}
            </div>
          </section>
        );
      })()}

      {/* refreshed whenever the page refreshes (the overall metrics object changes) */}
      <ImpactBand today={settings?.today} tick={metrics} />

      <nav className="tabs">
        <button className={tab === "attendee" ? "on" : ""} onClick={() => setTab("attendee")}>
          Attendee Mode ({counts.attendee}){counts.attendeeOpen > 0 && <span className="open">{needAction(counts.attendeeOpen)}</span>}
        </button>
        <button className={tab === "organizer" ? "on" : ""} onClick={() => setTab("organizer")}>
          Organizer Mode ({counts.organizer}){counts.organizerOpen > 0 && <span className="open">{needAction(counts.organizerOpen)}</span>}
        </button>
        <button className={tab === "proxy" ? "on" : ""} onClick={() => setTab("proxy")}>
          Proxy Requests ({counts.proxyRequests}){counts.proxyOpen > 0 && <span className="open">{needAction(counts.proxyOpen)}</span>}
        </button>
        <button className={tab === "past" ? "on" : ""} onClick={() => setTab("past")}>Past</button>
      </nav>

      <main>
        {tab === "attendee" && (allMine.length === 0 ? (
          <EmptyState title="No gaps">None of your meetings is affected by an absence, so nothing needs your action.</EmptyState>
        ) : (
          <Workspace label="Attendee Mode" {...pick("attendee")} keyOf={(i) => i.id} titleOf={(i) => i?.event.title}
            groups={[
              { id: "needs", label: "Needs action", items: attNeeds, attention: true,
                empty: { title: "All gaps closed", text: "Every affected meeting has a plan. Nothing needs your action." } },
              { id: "settled", label: "Settled", items: attSettled,
                empty: { title: "Nothing settled yet", text: "Meetings move here once a decision is made: a proxy accepts, you choose to attend or go on without you, or the meeting is rescheduled or canceled." } },
              { id: "none", label: "No action needed", items: attNone,
                empty: { title: "Nothing handled automatically", text: "Team check-ins and org-wide events that can go on without you appear here." } },
            ]}
            renderTile={(i) => <AttendeeTile item={i} people={people} me={shownId} />}
            renderDetail={(i) => (i.status === "rescheduled" || i.status === "cancelled"
              ? <SettledCard title={i.event.title} start={i.event.start} originalStart={i.originalStart} status={i.status}
                  decidedBy={i.decidedBy} people={people} />
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
                empty: { title: "All gaps closed", text: "Every affected meeting you organize has a plan. Nothing needs your action." } },
              { id: "settled", label: "Settled", items: settledMeetings,
                empty: { title: "Nothing settled yet", text: "Meetings move here once everyone who is out has a plan, or the meeting is rescheduled or canceled." } },
            ]}
            renderTile={(m) => <OrganizerTile meeting={m} people={people} />}
            renderDetail={(m) => (m.done
              ? <SettledCard title={m.event.title} start={m.event.start} originalStart={m.absentees[0]?.originalStart}
                  status={m.absentees[0]?.status} decidedBy={m.absentees[0]?.decidedBy} people={people} />
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
            renderDetail={(v) => <ProxyCard view={v} people={people} onRespond={respond} />}
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
              <ProxyCard key={v.request.id} view={v} people={people} activity={activityFor(v.item.id)} />
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
              ? `${scheduledWhere} for ${fmtWhen(when)}. Nobody required is out at that time.`
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
