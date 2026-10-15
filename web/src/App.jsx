import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { fmtDay, fmtRange, fmtWhen, needAction, plural } from "./format.js";
import MeetingCard from "./components/MeetingCard.jsx";
import OrganizerCard from "./components/OrganizerCard.jsx";
import ProxyCard from "./components/ProxyCard.jsx";
import ScheduleMeeting from "./components/ScheduleMeeting.jsx";
import SettledCard from "./components/SettledCard.jsx";
import MessageBar from "./components/MessageBar.jsx";
import DemoGuide from "./components/DemoGuide.jsx";
import Logo from "./components/Logo.jsx";
import ImpactBand from "./components/ImpactBand.jsx";
import { EmptyState, Icon } from "./components/Icons.jsx";
import { recall, remember } from "./storage.js";

const DEFAULT_PERSON = "p_priya";
// A link can open the app as someone, on a tab: ?as=p_sam&tab=organizer (handy for demos and the judges' guide).
const PARAMS = new URLSearchParams(window.location.search);
const TABS = ["attendee", "organizer", "proxy", "past"];

export default function App() {
  const [people, setPeople] = useState({});
  const [personId, setPersonId] = useState(PARAMS.get("as") || recall("personId") || DEFAULT_PERSON);
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
  const [showEmails, setShowEmails] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [notice, setNotice] = useState("");
  const [noticeAction, setNoticeAction] = useState(null); // optional button in the confirmation, e.g. "Open Sam's view"
  const [settings, setSettings] = useState(null); // from GET /settings/public
  const [activeIds, setActiveIds] = useState(null); // people with something to see; null = not loaded yet
  const [showGuide, setShowGuide] = useState(false);
  const [guideSeen, setGuideSeen] = useState(() => recall("guideSeen") === "1");   // "Start here" until opened once
  const [error, setError] = useState("");

  useEffect(() => {
    api("/people")
      .then((list) => setPeople(Object.fromEntries(list.map((p) => [p.id, p]))))
      .catch((e) => setError(e.message));
    // the few settings the screen shows, from the backend's config file, so the two never disagree
    api("/settings/public").then(setSettings).catch(() => {});
  }, []);

  const refresh = useCallback(async () => {
    try {
      setError("");
      const [m, a, att, org, pr, pi, pp, h, met, ob, act] = await Promise.all([
        api("/me", { person: personId }),
        api("/absences", { person: personId }),
        api("/items?mode=attendee", { person: personId }),
        api("/organizer/meetings", { person: personId }),   // one card per meeting
        api("/proxy-requests", { person: personId }),
        api("/items?mode=past", { person: personId }),
        api("/proxy-requests?past=true", { person: personId }),
        api("/history", { person: personId }),
        api("/metrics"),
        api("/dev/outbox"),
        api("/people/active"),   // who has something to see (for the "Signed in as" list)
      ]);
      setMe(m); setAbsences(a); setAttendee(att); setOrganizer(org); setProxyReqs(pr); setPastItems(pi); setPastProxy(pp);
      setHistory(h); setMetrics(met); setOutbox(ob); setActiveIds(act);
    } catch (e) {
      setError(e.message);
    }
  }, [personId]);

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
    remember("personId", id);
    setPersonId(id);
  }

  // Demo only: reload the demo data and clear the AI's cache, so every card is analysed again.
  async function resetDemo() {
    if (!window.confirm("Restore the sample data? Everything done so far is undone, and the AI analyzes every card again.")) return;
    try {
      await api("/dev/reset-demo", { method: "POST", person: personId });
      setNotice("Sample data restored. The AI is analyzing every card again.");
      await refresh();
    } catch (e) {
      setError(e.message);
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
  const clearError = useCallback(() => setError(""), []);
  const clearNotice = useCallback(() => { setNotice(""); setNoticeAction(null); }, []);
  const closeGuide = useCallback(() => setShowGuide(false), []);
  function openGuide() {
    setShowGuide(true);
    setGuideSeen(true);
    remember("guideSeen", "1");
  }
  // "Start with the first": the soonest card that still needs a decision, scrolled into view
  function goToFirst() {
    setTab("attendee");
    setTimeout(() => {
      const card = document.querySelector("main > article.attn-urgent, main > article.attn-soon, main > article.attn-open");
      card?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  }

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
    <>
      {/* Judges' demo controls: an add-on on top of the prototype (not part of the product), so a judge can switch
          people, see the emails the app sends, read the guide and restore the sample data. */}
      <div className="demo-toolbar" role="region" aria-label="Demo controls for judges">
        <div className="demo-toolbar-inner">
          <span className="demo-label">Judges' demo controls</span>
          <label className="demo-view-as">
            View as
            {/* only people with something to see (and whoever is viewed now), so nobody lands on an empty screen */}
            <select value={personId} onChange={(e) => switchPerson(e.target.value)}>
              {Object.values(people)
                .filter((p) => !p.isGroup && (!activeIds || activeIds.includes(p.id) || p.id === personId))
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <button onClick={openGuide} className={guideSeen ? "" : "guide-new"}>
            Demo guide{!guideSeen && <span className="start-here">Start here</span>}
          </button>
          <button onClick={resetDemo}
            title="Restores the sample people and meetings and clears the cache, so the AI analyzes every card again.">
            Reset sample data
          </button>
          <button onClick={() => setShowEmails((v) => !v)} aria-pressed={showEmails}>Emails sent ({outbox.length})</button>
        </div>
      </div>

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
        </div>
      </header>

      {showGuide && <DemoGuide onClose={closeGuide} />}

      <MessageBar kind="error" text={error} onClose={clearError} />
      <MessageBar kind="success" text={notice} onClose={clearNotice} hideAfter={settings?.messageHideSeconds ?? 6}
        action={noticeAction} />

      {/* The signed-in person's situation and next step, in two lines: the first thing a visitor reads. */}
      {upcomingAbsence && (() => {
        const open = counts.attendeeOpen;
        const firstName = (people[personId]?.name || "").split(" ")[0];
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
            {open > 0 && <button onClick={goToFirst}>Start with the first ↓</button>}
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
        {tab === "attendee" && (
          <>
            {attendee.needsAction.length === 0 && noActionCount === 0 && (
              <EmptyState title="No gaps">None of your meetings is affected by an absence, so nothing needs your action.</EmptyState>
            )}
            {/* decided cards stay listed (people may change their mind), so "all closed" = nothing still needs a decision */}
            {(attendee.needsAction.length > 0 || noActionCount > 0) && !attendee.needsAction.some((i) => i.needsAttention) && (
              <EmptyState title="All gaps closed">Every affected meeting has a plan. Nothing needs your action.</EmptyState>
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
                {settled.length > 0 && <h4>Rescheduled or canceled</h4>}
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
            {activeMeetings.length === 0 && doneMeetings.length === 0 && (
              <EmptyState title="No gaps">None of the meetings you organize is affected by an absence.</EmptyState>
            )}
            {openMeetings.length === 0 && (settledMeetings.length > 0 || doneMeetings.length > 0) && (
              <EmptyState title="All gaps closed">Every affected meeting you organize has a plan. Nothing needs your action.</EmptyState>
            )}
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
            {proxyReqs.length === 0 && <EmptyState title="No proxy requests">Nobody has asked you to cover a meeting.</EmptyState>}
            {proxyReqs.length > 0 && waitingReqs.length === 0 && (
              <EmptyState title="All answered">You've answered every request to cover a meeting.</EmptyState>
            )}
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
          <h4>Emails sent (demo: shown here instead of real inboxes)</h4>
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
          onClose={() => setShowSchedule(false)}
          onDone={async (result, when) => {
            setShowSchedule(false);
            const out = result.affected.map((i) => people[i.absentPersonId]?.name.split(" ")[0]).filter(Boolean);
            const who = out.length === 1 ? `${out[0]} is` : `${out.slice(0, -1).join(", ")} and ${out.at(-1)} are`;
            setNoticeAction(null);
            setNotice(out.length === 0
              ? `Meeting scheduled for ${fmtWhen(when)}. Nobody required is out at that time.`
              : `Meeting scheduled for ${fmtWhen(when)}, but ${who} out that day. It's in your Organizer Mode, ready for a decision.`);
            if (out.length > 0) setTab("organizer");
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
