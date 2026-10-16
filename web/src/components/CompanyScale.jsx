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
    ["Key meetings missed through leave", (r) => n(r.affectedMeetings), `${p.leaveDaysPerYear} leave days a year × ${p.keyMeetingsPerLeaveDay} key meetings a day`],
    ["Team time saved", (r) => `${n(r.hoursSaved)} h`, `${pct(p.shareClosedEarly)} covered, rescheduled or canceled in time × ${p.peoplePerMeeting} people × ${p.minutesSavedPerPerson} min`],
    ["Value of that time", (r) => money(r.value), `at ${p.currency}${p.hourlyCost} an hour`],
    ["Decisions kept on schedule", (r) => n(r.decisionsOnSchedule), `${pct(p.shareWentAhead)} went ahead with a proxy or without them`],
    ["Days of waiting avoided", (r) => n(r.daysWaitingAvoided), `${p.daysWaitingAvoided} days each, until the person is back`],
  ];

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal scale" role="dialog" aria-modal="true" aria-labelledby="scale-title" onClick={(e) => e.stopPropagation()}>
        <header className="guide-head">
          <h3 id="scale-title">At company scale, per year</h3>
          <button className="message-close" onClick={onClose} aria-label="Close" autoFocus>✕</button>
        </header>
        {error && <div className="note warn">{error}</div>}
        {!p && !error && <p className="reason">Loading…</p>}
        {p && (
          <>
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
              <b>An estimate, not a measurement.</b>{" "}
              {p.measured
                ? `The shares, people per meeting and days of waiting are measured from the ${p.meetingsMeasured} meetings this app has handled; `
                : "Too few meetings handled yet, so the shares and people per meeting are typical values from the config; "}
              leave days, meetings per day of leave and the hourly cost are assumptions you can change. Time saved counts only
              the start everyone would waste joining, waiting and giving up ({p.minutesSavedPerPerson} min each); meetings that go
              ahead anyway count nothing. In production, the rates come from your own company's meetings.
            </p>
          </>
        )}
      </section>
    </div>,
    document.body,
  );
}
