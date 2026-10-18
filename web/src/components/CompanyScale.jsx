import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api.js";

const n = (x) => Math.round(x).toLocaleString("en-US");
const pct = (x) => `${Math.round(x * 100)}%`;

// "At company scale": what the rates measured in this app would mean for a whole company. An estimate, labelled so;
// the assumptions are shown under the table and set in [metrics.projection] in the config. Rendered at the page's top
// level (a portal): inside the glass band, its blur would trap the overlay.
export default function CompanyScale({ onClose }) {
  const [p, setP] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/metrics/projection").then(setP).catch((e) => setError(e.message));
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const money = (x) => `${p.currency}${x >= 1e6 ? `${(x / 1e6).toFixed(1)}M` : x >= 1e3 ? `${Math.round(x / 1e3)}K` : n(x)}`;
  const ROWS = p && [
    ["Key meetings missed through leave", (r) => n(r.affectedMeetings), `${p.leaveDaysPerYear} leave days a year × ${p.keyMeetingsPerLeaveDay} key meeting${p.keyMeetingsPerLeaveDay === 1 ? "" : "s"} a day`],
    ["Team time saved", (r) => `${n(r.hoursSaved)} h`, `${pct(p.shareClosedEarly)} covered, rescheduled or canceled in time × ${p.peoplePerMeeting} people on average × ${p.minutesSavedPerPerson} min`],
    ["Value of that time", (r) => money(r.value), `at ${p.currency}${p.hourlyCost} an hour`],
    ["Decisions kept on schedule", (r) => n(r.decisionsOnSchedule), `${pct(p.shareWentAhead)} went ahead with a proxy or without them`],
    ["Days of waiting avoided", (r) => n(r.daysWaitingAvoided), `${p.daysWaitingAvoided} days each, until the person is back`],
  ];

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal scale" role="dialog" aria-modal="true" aria-labelledby="scale-title" onClick={(e) => e.stopPropagation()}>
        <header className="guide-head">
          <h3 id="scale-title">At company scale, per year (illustrative)</h3>
          <button className="message-close" onClick={onClose} aria-label="Close" autoFocus>✕</button>
        </header>
        {error && <div className="note warn">{error}</div>}
        {!p && !error && <p className="reason">Loading…</p>}
        {p && (
          <>
            <p className="scale-one">
              <b>Start with one meeting.</b> When a meeting of {Math.round(p.peoplePerMeeting)} people is covered, moved or
              canceled in time, each of them is spared about {p.minutesSavedPerPerson} minutes of joining, waiting and
              giving up: {Math.round(p.peoplePerMeeting)} × {p.minutesSavedPerPerson} = {Math.round(p.peoplePerMeeting) * p.minutesSavedPerPerson} minutes
              in all. The table below multiplies that by a company's size.
            </p>
            <div className="scale-wrap">
              <table className="scale-table">
                <thead>
                  <tr><th scope="col">Company size</th>{p.rows.map((r) => <th key={r.employees} scope="col">{n(r.employees)} people</th>)}</tr>
                </thead>
                <tbody>
                  {ROWS.map(([label, cell, how], k) => (
                    <tr key={label} className={k === 1 || k === 3 ? "scale-key" : ""}>
                      <th scope="row">{label}<small>{how}</small></th>
                      {p.rows.map((r) => <td key={r.employees}>{cell(r)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="scale-note">
              <b>An illustrative model, not a forecast.</b> It assumes a typical meeting has about{" "}
              {Math.round(p.peoplePerMeeting)} people, and that when a key person is missing everyone loses at least{" "}
              {p.minutesSavedPerPerson} minutes: a couple of minutes to join, then waiting and pinging the missing person
              before giving up. Each person has about {p.leaveDaysPerYear} days of leave a year and is the key person in
              about {p.keyMeetingsPerLeaveDay} meeting{p.keyMeetingsPerLeaveDay === 1 ? "" : "s"} per day of leave (senior
              roles have more). Time is valued at {p.currency}{p.hourlyCost} an hour.{" "}
              {p.measured
                ? `The shares handled in time and the people per meeting come from the ${p.meetingsMeasured} meetings decided in this app so far, so they change as people decide.`
                : "Too few meetings are decided yet, so typical values are used for the shares and the people per meeting."}{" "}
              It counts only the minutes lost waiting, not the cost of breaking off focused work or another meeting to
              join; meetings that go ahead anyway count nothing. Every assumption is a setting you can change.
            </p>
          </>
        )}
      </section>
    </div>,
    document.body,
  );
}
