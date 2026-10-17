import { useState } from "react";
import { fmtWhen, fromIst, istFields } from "../format.js";

// The organizer's reschedule: the proposed time in one click ("Reschedule to Mon, 9 Nov · 3:00 pm IST"), or a time
// they pick themselves, also when no time was found. The backend checks a picked time (in the future, on a day
// everyone who is out is back) and moves the Google event once for everyone.
export default function ReschedulePanel({ proposal, currentStart, busy, onConfirm, onBack }) {
  const none = proposal.none;
  const [picking, setPicking] = useState(none);
  // the picker starts at the proposed time, or a week after the current time when nothing was proposed
  const startAt = none ? new Date(new Date(currentStart).getTime() + 7 * 86400000).toISOString() : proposal.proposedStart;
  const [date, setDate] = useState(istFields(startAt).date);
  const [time, setTime] = useState(istFields(startAt).time);
  const picked = date && time ? fromIst(date, time) : null;

  return (
    <div className="panel reschedule-panel">
      {none ? (
        <p>No time works for everyone in the next few working days. Pick a time yourself:</p>
      ) : (
        <p>
          Proposed: <b>{fmtWhen(proposal.proposedStart)}</b>
          {proposal.flagged ? " (a little off the original time of day)" : ""}. Everyone who is out will be back, and
          every key person is free.
        </p>
      )}

      {!picking && (
        <div className="actions">
          <button className="primary" disabled={busy} onClick={() => onConfirm(null)}>
            Reschedule to {fmtWhen(proposal.proposedStart)}
          </button>
          <button className="small" disabled={busy} onClick={() => setPicking(true)}>Pick another time</button>
          <button className="link" onClick={onBack}>Back</button>
        </div>
      )}

      {picking && (
        <form className="pick-time" onSubmit={(e) => { e.preventDefault(); if (picked) onConfirm(picked); }}>
          <div className="row">
            <label>Date <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
            <label>Time (IST) <input type="time" value={time} onChange={(e) => setTime(e.target.value)} required /></label>
          </div>
          <p className="reason">
            The new day must be one when everyone who is out is back. Whether people are free at that hour is up to you;
            Google Calendar tells the guests.
          </p>
          <div className="actions">
            <button className="primary" type="submit" disabled={busy || !picked}
              title={picked ? undefined : "Pick a date and a time first."}>
              {picked ? `Reschedule to ${fmtWhen(picked)}` : "Reschedule"}
            </button>
            {none && (
              <button type="button" className="small" disabled={busy} onClick={() => onConfirm(null)}>
                Note that no time works
              </button>
            )}
            <button type="button" className="link" onClick={none ? onBack : () => setPicking(false)}>Back</button>
          </div>
        </form>
      )}
    </div>
  );
}
