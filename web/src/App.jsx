import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { fmtDay, fmtWhen } from "./format.js";
import MeetingCard from "./components/MeetingCard.jsx";
import ProxyCard from "./components/ProxyCard.jsx";
import ScheduleMeeting from "./components/ScheduleMeeting.jsx";

const DEFAULT_PERSON = "p_priya";

export default function App() {
  const [people, setPeople] = useState({});
  const [personId, setPersonId] = useState(localStorage.getItem("personId") || DEFAULT_PERSON);
  const [me, setMe] = useState(null);
  const [absences, setAbsences] = useState([]);
  const [attendee, setAttendee] = useState({ needsAction: [], noActionNeeded: { teamCheckins: [], orgEvents: [] } });
  const [organizer, setOrganizer] = useState([]);
  const [proxyReqs, setProxyReqs] = useState([]);
  const [pastItems, setPastItems] = useState([]);
  const [pastProxy, setPastProxy] = useState([]);
  const [history, setHistory] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [outbox, setOutbox] = useState([]);
  const [tab, setTab] = useState("attendee");
  const [showEmails, setShowEmails] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api("/people")
      .then((list) => setPeople(Object.fromEntries(list.map((p) => [p.id, p]))))
      .catch((e) => setError(`Cannot reach the backend: ${e.message}. Is it running on port 8000?`));
  }, []);

  const refresh = useCallback(async () => {
    try {
      setError("");
      const [m, a, att, org, pr, pi, pp, h, met, ob] = await Promise.all([
        api("/me", { person: personId }),
        api("/absences", { person: personId }),
        api("/items?mode=attendee", { person: personId }),
        api("/items?mode=organizer", { person: personId }),
        api("/proxy-requests", { person: personId }),
        api("/items?mode=past", { person: personId }),
        api("/proxy-requests?past=true", { person: personId }),
        api("/history", { person: personId }),
        api("/metrics"),
        api("/dev/outbox"),
      ]);
      setMe(m); setAbsences(a); setAttendee(att); setOrganizer(org); setProxyReqs(pr); setPastItems(pi); setPastProxy(pp);
      setHistory(h); setMetrics(met); setOutbox(ob);
    } catch (e) {
      setError(`Cannot reach the backend: ${e.message}. Is it running on port 8000?`);
    }
  }, [personId]);

  useEffect(() => { refresh(); }, [refresh]);

  function switchPerson(id) {
    localStorage.setItem("personId", id);
    setPersonId(id);
  }

  async function respond(reqId, response) {
    try {
      await api(`/proxy-requests/${reqId}/respond`, { method: "POST", person: personId, body: { response } });
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  const counts = me?.counts || { attendee: 0, organizer: 0, proxyRequests: 0, attendeeOpen: 0, organizerOpen: 0, proxyOpen: 0 };
  // Activity log lines per meeting, shown inside the cards in Past
  const activityFor = (itemId) => history.filter((h) => h.itemId === itemId).sort((a, b) => a.at.localeCompare(b.at));
  const noAction = attendee.noActionNeeded;
  const noActionCount = noAction.teamCheckins.length + noAction.orgEvents.length;
  const upcomingAbsence = absences[0];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand">Close the Gap</div>
          <div className="tagline">Spot the gap early. Keep the meeting going.</div>
        </div>
        <div className="topbar-right">
          <button className="ghost" onClick={() => setShowSchedule(true)}>Schedule a meeting</button>
          <button className="ghost" onClick={() => setShowAdd(true)}>Report an absence</button>
          <button className="ghost" onClick={() => setShowEmails((v) => !v)}>Emails (demo) · {outbox.length}</button>
          <label className="switcher">
            Signed in as
            <select value={personId} onChange={(e) => switchPerson(e.target.value)}>
              {Object.values(people).filter((p) => p.id !== "p_events").map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {error && <div className="banner warn">{error}</div>}
      {notice && <div className="banner warn" onClick={() => setNotice("")}>{notice}</div>}

      {upcomingAbsence && (
        <div className="banner">
          You're out <b>{fmtDay(upcomingAbsence.start)} – {fmtDay(upcomingAbsence.end)}</b>.{" "}
          {attendee.needsAction.length + noActionCount} meetings are affected; {counts.attendeeOpen} need action.
        </div>
      )}

      {metrics && (
        <div className="impact">
          <div><b>{metrics.meetingsResolved}</b><span>meetings resolved</span></div>
          <div><b>{metrics.avgLeadTimeDays}</b><span>days ahead on average</span></div>
          <div><b>{metrics.attendeeMinutesSaved}</b><span>attendee-minutes saved (modeled)</span></div>
        </div>
      )}

      <nav className="tabs">
        <button className={tab === "attendee" ? "on" : ""} onClick={() => setTab("attendee")}>
          Attendee Mode ({counts.attendee}){counts.attendeeOpen > 0 && <span className="open">{counts.attendeeOpen} need action</span>}
        </button>
        <button className={tab === "organizer" ? "on" : ""} onClick={() => setTab("organizer")}>
          Organizer Mode ({counts.organizer}){counts.organizerOpen > 0 && <span className="open">{counts.organizerOpen} need action</span>}
        </button>
        <button className={tab === "proxy" ? "on" : ""} onClick={() => setTab("proxy")}>
          Proxy Requests ({counts.proxyRequests}){counts.proxyOpen > 0 && <span className="open">{counts.proxyOpen} need action</span>}
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
              <details className="no-action">
                <summary>No action needed ({noActionCount})</summary>
                {noAction.teamCheckins.length > 0 && <h4>Team check-ins</h4>}
                {noAction.teamCheckins.map((i) => (
                  <MeetingCard key={i.id} item={i} people={people} me={personId} role="attendee" refresh={refresh} quiet />
                ))}
                {noAction.orgEvents.length > 0 && <h4>Org-wide events</h4>}
                {noAction.orgEvents.map((i) => (
                  <MeetingCard key={i.id} item={i} people={people} me={personId} role="attendee" refresh={refresh} quiet />
                ))}
              </details>
            )}
          </>
        )}

        {tab === "organizer" && (
          <>
            {organizer.length === 0 && <div className="empty">No gaps in meetings you organize.</div>}
            {organizer.map((i) => (
              <MeetingCard key={i.id} item={i} people={people} me={personId} role="organizer" refresh={refresh} />
            ))}
          </>
        )}

        {tab === "proxy" && (
          <>
            {proxyReqs.length === 0 && <div className="empty">No proxy requests.</div>}
            {proxyReqs.map((v) => (
              <ProxyCard key={v.request.id} view={v} people={people} onRespond={respond} />
            ))}
          </>
        )}

        {tab === "past" && (
          <>
            <p className="reason">Meetings whose time has passed, kept for 30 days.</p>
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
          onClose={() => setShowSchedule(false)}
          onDone={async (result) => {
            setShowSchedule(false);
            const n = result.affected.length;
            setNotice(n === 0
              ? "Meeting scheduled. Everyone required is available."
              : `Meeting scheduled, but ${n} key ${n === 1 ? "person is" : "people are"} already out that day. You were emailed (see Emails). Open Organizer Mode to reschedule or name a proxy.`);
            if (n > 0) setTab("organizer");
            await refresh();
          }}
        />
      )}

      {showAdd && (
        <AddAbsence
          people={people}
          me={personId}
          onClose={() => setShowAdd(false)}
          onDone={async () => { setShowAdd(false); await refresh(); }}
        />
      )}
    </div>
  );
}

function AddAbsence({ people, me, onClose, onDone }) {
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
        <p className="reason">If it starts within 24 hours it is treated as a sudden absence; otherwise it is planned leave.</p>
        {error && <div className="note warn">{error}</div>}
        <div className="actions">
          <button className="primary" type="submit">Save</button>
          <button type="button" className="link" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
