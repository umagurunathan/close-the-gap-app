import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { fmtDay, fmtWhen, needAction, plural } from "./format.js";
import MeetingCard from "./components/MeetingCard.jsx";
import OrganizerCard from "./components/OrganizerCard.jsx";
import ProxyCard from "./components/ProxyCard.jsx";
import ScheduleMeeting from "./components/ScheduleMeeting.jsx";
import SettledCard from "./components/SettledCard.jsx";
import MessageBar from "./components/MessageBar.jsx";
import { useAuth } from "./AuthGate.jsx";
import { publicDemoMode } from "./firebase.js";

const DEFAULT_PERSON = "p_priya";
// A link can open the app as someone, on a tab: ?as=p_sam&tab=organizer (handy for demos and the judges' guide).
const PARAMS = new URLSearchParams(window.location.search);
const TABS = ["attendee", "organizer", "proxy", "past"];

export default function App() {
  const { enabled: firebaseAuthEnabled, user: firebaseUser, signOut } = useAuth();
  const [people, setPeople] = useState({});
  const [personId, setPersonId] = useState(firebaseAuthEnabled
    ? ""
    : PARAMS.get("as") || localStorage.getItem("personId") || DEFAULT_PERSON);
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
  const [settings, setSettings] = useState(null); // from GET /settings/public
  const [dataMode, setDataMode] = useState(null);
  const dataModeRef = useRef(null);
  const [switchingDataMode, setSwitchingDataMode] = useState(false);
  const [error, setError] = useState("");

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
      setNotice(calendarResult === "connected"
        ? "Google Calendar connected. Sync your calendar to find meetings affected by your absence."
        : "Google Calendar connection failed. Check OAuth setup and try again.");
      url.searchParams.delete("calendar");
      window.history.replaceState({}, "", url);
    }
  }, []);

  useEffect(() => {
    if (firebaseAuthEnabled && !firebaseUser) return;
    api("/people")
      .then((list) => setPeople(Object.fromEntries(list.map((p) => [p.id, p]))))
      .catch((e) => setError(e.message));
    // the few settings the screen shows, from the backend's config file, so the two never disagree
    api("/settings/public").then(setSettings).catch(() => {});
  }, [firebaseAuthEnabled, firebaseUser]);

  useEffect(() => {
    if (firebaseAuthEnabled && !firebaseUser) return undefined;
    let active = true;
    const loadMode = () => api("/data-mode").then((mode) => {
      if (!active) return;
      if (dataModeRef.current && dataModeRef.current !== mode.mode) {
        window.location.reload();
        return;
      }
      dataModeRef.current = mode.mode;
      setDataMode(mode);
    }).catch((e) => {
      if (active) setError(e.message);
    });
    loadMode();
    const timer = window.setInterval(loadMode, 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [firebaseAuthEnabled, firebaseUser]);

  const refresh = useCallback(async () => {
    try {
      setError("");
      const m = await api("/me", { person: firebaseAuthEnabled ? undefined : personId });
      const activePersonId = firebaseAuthEnabled ? m.person.id : personId;
      if (firebaseAuthEnabled) setPersonId(activePersonId);
      const [a, att, org, pr, pi, pp, h, met, ob, cal] = await Promise.all([
        api("/absences", { person: activePersonId }),
        api("/items?mode=attendee", { person: activePersonId }),
        api("/organizer/meetings", { person: activePersonId }),   // one card per meeting
        api("/proxy-requests", { person: activePersonId }),
        api("/items?mode=past", { person: activePersonId }),
        api("/proxy-requests?past=true", { person: activePersonId }),
        api("/history", { person: activePersonId }),
        api("/metrics"),
        firebaseAuthEnabled ? Promise.resolve([]) : api("/dev/outbox"),
        api("/integrations/google-calendar/status", { person: activePersonId }),
      ]);
      setMe(m); setAbsences(a); setAttendee(att); setOrganizer(org); setProxyReqs(pr); setPastItems(pi); setPastProxy(pp);
      setHistory(h); setMetrics(met); setOutbox(ob); setCalendarStatus(cal);
    } catch (e) {
      setError(e.message);
    }
  }, [personId, firebaseAuthEnabled]);

  useEffect(() => { refresh(); }, [refresh]);

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
    localStorage.setItem("personId", id);
    setPersonId(id);
  }

  // Demo only: reload the demo data and clear the AI's cache, so every card is analysed again.
  async function resetDemo() {
    if (!window.confirm("Reset the demo? Everything done so far is undone, and the AI analyses every card again.")) return;
    try {
      await api("/dev/reset-demo", { method: "POST", person: personId });
      setNotice("Demo reset. The AI is analysing every card again.");
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  async function switchDataMode(mode) {
    const label = mode === "firestore" ? "Calendar + Firestore" : "Seed file";
    if (!window.confirm(`Switch the entire demo to ${label}? This changes the data source for everyone using the app.`)) return;
    setSwitchingDataMode(true);
    try {
      const result = await api("/data-mode", { method: "POST", body: { mode } });
      dataModeRef.current = result.mode;
      setDataMode(result);
      setNotice(mode === "firestore"
        ? "Connected demo selected. Seed JSON initializes missing Firestore data; existing data is preserved."
        : "Seed demo selected. The in-memory demo was reloaded from the seed JSON.");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setSwitchingDataMode(false);
    }
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
  const clearNotice = useCallback(() => setNotice(""), []);

  const counts = me?.counts || { attendee: 0, organizer: 0, proxyRequests: 0, attendeeOpen: 0, organizerOpen: 0, proxyOpen: 0 };
  // Activity log lines per meeting, shown inside the cards in Past
  const activityFor = (itemId) => history.filter((h) => h.itemId === itemId).sort((a, b) => a.at.localeCompare(b.at));
  const noAction = attendee.noActionNeeded;
  const settled = noAction.rescheduledOrCancelled || [];   // rescheduled or cancelled: the gap is closed
  const noActionCount = noAction.teamCheckins.length + noAction.orgEvents.length + settled.length;
  const affectedCount = attendee.needsAction.length + noAction.teamCheckins.length + noAction.orgEvents.length;
  const activeMeetings = organizer.filter((m) => !m.done);
  const doneMeetings = organizer.filter((m) => m.done);
  // Needs action first, the most urgent on top (red, then amber, then by date); settled ones below, by date.
  const URGENCY = { urgent: 0, soon: 1 };
  const openMeetings = activeMeetings.filter((m) => m.needsAttention)
    .sort((a, b) => (URGENCY[a.urgency] ?? 2) - (URGENCY[b.urgency] ?? 2) || a.event.start.localeCompare(b.event.start));
  const settledMeetings = activeMeetings.filter((m) => !m.needsAttention);
  // Proxy requests: waiting for your answer first, then the ones you answered.
  const waitingReqs = proxyReqs.filter((v) => v.request.status === "pending");
  const answeredReqs = proxyReqs.filter((v) => v.request.status !== "pending");
  const upcomingAbsence = absences[0];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand">Close the Gap</div>
          <div className="tagline">Spot the gap early. Keep the meeting going.</div>
        </div>
        <div className="topbar-right">
          {publicDemoMode && <a className="ghost" href="/">Sign in for connected demo</a>}
          {dataMode?.canSwitch && <div className="data-mode" aria-label="Global demo data source">
            <span>Data source</span>
            <button className={dataMode.mode === "memory" ? "mode-active" : ""}
              aria-pressed={dataMode.mode === "memory"} disabled={switchingDataMode || dataMode.mode === "memory"}
              onClick={() => switchDataMode("memory")}>
              Seed file
            </button>
            <button className={dataMode.mode === "firestore" ? "mode-active" : ""}
              aria-pressed={dataMode.mode === "firestore"} disabled={switchingDataMode || dataMode.mode === "firestore"}
              onClick={() => switchDataMode("firestore")}>
              Calendar + Firestore
            </button>
          </div>}
          <button className="ghost" onClick={() => setShowSchedule(true)}>Schedule a meeting</button>
          <button className="ghost" onClick={() => setShowAdd(true)}>Report an absence</button>
          {!publicDemoMode && (calendarStatus.connected ? (
            <button className="ghost" onClick={syncCalendar}>Sync Google Calendar</button>
          ) : (
            <button className="ghost" onClick={connectCalendar} disabled={!calendarStatus.configured}>
              Connect Google Calendar
            </button>
          ))}
          {!firebaseAuthEnabled && <>
            <button className="ghost" onClick={() => setShowEmails((v) => !v)}>Emails (demo) · {outbox.length}</button>
            <button className="ghost" onClick={resetDemo}
              title="Back to the demo data, with nothing cached: the AI analyses every card again">Reset demo</button>
            <label className="switcher">
              Signed in as
              <select value={personId} onChange={(e) => switchPerson(e.target.value)}>
                {Object.values(people).filter((p) => p.id !== "p_events").map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </label>
          </>}
          {firebaseAuthEnabled && <div className="signed-in">
            <span>{firebaseUser?.email}</span>
            <button className="ghost" onClick={signOut}>Sign out</button>
          </div>}
        </div>
      </header>

      {publicDemoMode && <div className="public-demo-banner">
        Public seed demo · changes are temporary and shared with other visitors. Google Calendar and Firestore are not connected.
      </div>}
      <MessageBar kind="error" text={error} onClose={clearError} />
      <MessageBar kind="success" text={notice} onClose={clearNotice} hideAfter={settings?.messageHideSeconds ?? 6} />

      {upcomingAbsence && (
        <div className="banner">
          You're out <b>{fmtDay(upcomingAbsence.start)} – {fmtDay(upcomingAbsence.end)}</b>.{" "}
          {plural(affectedCount, "meeting is", "meetings are")} affected; {needAction(counts.attendeeOpen)}.
        </div>
      )}

      {metrics && (
        <section className="impact" aria-label="Impact so far">
          <div title="Meetings affected by someone's absence that already have a plan: handled automatically, covered by a proxy, going ahead without them, rescheduled or cancelled.">
            <b>{metrics.meetingsWithPlan}<small> of {metrics.meetingsAffected}</small></b>
            <span>Affected meetings with a plan</span>
          </div>
          <div title="On average, how many days before the meeting the plan was made, instead of finding out when the meeting starts.">
            <b>{metrics.avgNoticeDays}<small> days</small></b>
            <span>Notice, on average</span>
          </div>
          <div title={metrics.estimateNote}>
            <b>{metrics.teamHoursSaved}<small> h</small></b>
            <span>Team time saved (estimate)</span>
          </div>
          <div title={metrics.decisionsCounted
            ? `Of the ${metrics.decisionsCounted} decisions people made, how many followed the recommendation shown on the card.`
            : "No decisions yet: this shows how often people follow the recommendation shown on the card."}>
            <b>{metrics.recommendationsFollowedPct ?? "–"}{metrics.recommendationsFollowedPct != null && <small>%</small>}</b>
            <span>Recommendations followed</span>
          </div>
        </section>
      )}

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
        {tab === "attendee" && (
          <>
            {attendee.needsAction.length === 0 && noActionCount === 0 && (
              <div className="empty">No gaps. Nothing needs your action.</div>
            )}
            {attendee.needsAction.map((i) => (
              <MeetingCard key={i.id} item={i} people={people} me={personId} role="attendee" refresh={refresh} />
            ))}
            {noActionCount > 0 && (
              // open by itself when it is all there is, so the page is never just a closed line
              <details className="no-action" open={attendee.needsAction.length === 0}>
                <summary>No action needed ({noActionCount})</summary>
                {noAction.teamCheckins.length > 0 && <h4>Team check-ins</h4>}
                {noAction.teamCheckins.map((i) => (
                  <MeetingCard key={i.id} item={i} people={people} me={personId} role="attendee" refresh={refresh} quiet />
                ))}
                {noAction.orgEvents.length > 0 && <h4>Org-wide events</h4>}
                {noAction.orgEvents.map((i) => (
                  <MeetingCard key={i.id} item={i} people={people} me={personId} role="attendee" refresh={refresh} quiet />
                ))}
                {settled.length > 0 && <h4>Rescheduled or cancelled</h4>}
                {settled.map((i) => (
                  <SettledCard key={i.id} title={i.event.title} start={i.event.start} originalStart={i.originalStart}
                    status={i.status} decidedBy={i.decidedBy} people={people} />
                ))}
              </details>
            )}
          </>
        )}

        {tab === "organizer" && (
          <>
            {activeMeetings.length === 0 && <div className="empty">No gaps in meetings you organize.</div>}
            {openMeetings.map((m) => (
              <OrganizerCard key={m.calendarEventId} meeting={m} people={people} me={personId} refresh={refresh} />
            ))}
            {settledMeetings.length > 0 && <h4 className="group-title">Settled ({settledMeetings.length})</h4>}
            {settledMeetings.map((m) => (
              <OrganizerCard key={m.calendarEventId} meeting={m} people={people} me={personId} refresh={refresh} />
            ))}
            {doneMeetings.length > 0 && (
              <details className="no-action" open={activeMeetings.length === 0}>
                <summary>Done ({doneMeetings.length})</summary>
                {doneMeetings.map((m) => (
                  <SettledCard key={m.calendarEventId} title={m.event.title} start={m.event.start}
                    originalStart={m.absentees[0]?.originalStart} status={m.absentees[0]?.status}
                    decidedBy={m.absentees[0]?.decidedBy} people={people} />
                ))}
              </details>
            )}
          </>
        )}

        {tab === "proxy" && (
          <>
            {proxyReqs.length === 0 && <div className="empty">No proxy requests.</div>}
            {waitingReqs.map((v) => (
              <ProxyCard key={v.request.id} view={v} people={people} onRespond={respond} />
            ))}
            {answeredReqs.length > 0 && <h4 className="group-title">Answered ({answeredReqs.length})</h4>}
            {answeredReqs.map((v) => (
              <ProxyCard key={v.request.id} view={v} people={people} onRespond={respond} />
            ))}
          </>
        )}

        {tab === "past" && (
          <>
            <p className="reason">Meetings whose time has passed{settings ? `, kept for ${settings.pastDays} days` : ""}.</p>
            {pastItems.length === 0 && pastProxy.length === 0 && <div className="empty">Nothing in the past yet.</div>}
            {pastItems.length > 0 && <h4 className="group-title">Your meetings</h4>}
            {pastItems.map((i) => (
              <MeetingCard
                key={i.id} item={i} people={people} me={personId}
                role={i.absentPersonId === personId ? "attendee" : "organizer"}
                refresh={refresh} readOnly activity={activityFor(i.id)}
              />
            ))}
            {pastProxy.length > 0 && <h4 className="group-title">Meetings you covered</h4>}
            {pastProxy.map((v) => (
              <ProxyCard key={v.request.id} view={v} people={people} activity={activityFor(v.item.id)} />
            ))}
          </>
        )}
      </main>

      {showEmails && (
        <aside className="drawer">
          <h4>Emails the app "sent" (demo)</h4>
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
          people={people}
          me={personId}
          calendarConnected={calendarStatus.connected}
          onClose={() => setShowSchedule(false)}
          onDone={async (result) => {
            setShowSchedule(false);
            const n = result.affected.length;
            const scheduledWhere = result.calendarProvider === "google"
              ? "Google Calendar updated"
              : "Demo calendar updated";
            setNotice(n === 0
              ? `${scheduledWhere}. Everyone required is available.`
              : `${scheduledWhere}, but ${n} key ${n === 1 ? "person is" : "people are"} already out that day. You were emailed (see Emails). Open Organizer Mode to reschedule or name a proxy.`);
            if (n > 0) setTab("organizer");
            await refresh();
          }}
        />
      )}

      {showAdd && (
        <AddAbsence
          suddenHours={settings?.suddenNoticeHours}
          people={people}
          me={personId}
          onClose={() => setShowAdd(false)}
          onDone={async () => { setShowAdd(false); await refresh(); }}
        />
      )}
    </div>
  );
}

function AddAbsence({ people, me, onClose, onDone, suddenHours }) {
  const [form, setForm] = useState({ personId: me, start: "2026-10-27", end: "2026-10-28" });
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    try {
      await api("/absences", { method: "POST", person: me, body: form });
      onDone();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Report an absence</h3>
        <label>Who is out
          <select value={form.personId} onChange={(e) => setForm({ ...form, personId: e.target.value })}>
            {Object.values(people).filter((p) => p.id !== "p_events").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>From <input type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></label>
        <label>To <input type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></label>
        <p className="reason">If it starts within {suddenHours ?? 24} hours it is treated as a sudden absence; otherwise it is planned leave.</p>
        {error && <div className="note warn">{error}</div>}
        <div className="actions">
          <button className="primary" type="submit">Save</button>
          <button type="button" className="link" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
