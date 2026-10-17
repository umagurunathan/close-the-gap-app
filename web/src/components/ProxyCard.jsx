import { useCallback, useState } from "react";
import { fmtWhen, urgencyChip } from "../format.js";
import { Icon } from "./Icons.jsx";
import Invitees from "./Invitees.jsx";
import SummariesDialog, { SummariesLink } from "./Summaries.jsx";

const STATUS = {
  pending: { text: "Waiting for your answer", cls: "status-proxy_requested" },
  accepted: { text: "You accepted", cls: "status-proxy_accepted" },
  declined: { text: "You declined", cls: "status-proxy_declined" },
  withdrawn: { text: "No longer needed", cls: "chip-tag" },
};

// A proxy request, as the person asked to cover sees it. It stays visible after they answer, until the meeting
// has passed; then it moves to Past. `onRespond` is null on finished meetings (read-only).
export default function ProxyCard({ view, people, me, onRespond = null, activity = [] }) {
  const { request: r, item, notesAvailable } = view;
  const [busy, setBusy] = useState(false);   // locked while the answer is being sent: no double answers
  const [showSummaries, setShowSummaries] = useState(false);
  const closeSummaries = useCallback(() => setShowSummaries(false), []);
  // The proxy reads the agenda and the summaries shared with them, like any invitee (read-only)
  const invited = item.event.organizerId === me || item.event.attendees.some((a) => a.personId === me);
  async function answer(response) {
    setBusy(true);
    try {
      await onRespond(r.id, response);
    } finally {
      setBusy(false);
    }
  }
  const name = (id) => people[id]?.name ?? id;
  const st = STATUS[r.status];
  const urgency = r.status === "pending" ? urgencyChip(item.urgency, item.hoursToStart) : null;
  const meetingChange =
    item.status === "rescheduled" ? "Meeting was rescheduled" : item.status === "cancelled" ? "Meeting was canceled" : null;

  return (
    <article className="card">
      <header className="card-head">
        <div>
          <h3>{item.event.title}</h3>
          <div className="when"><Icon name="calendar" size={14} />{fmtWhen(item.event.start)}</div>
        </div>
        <div className="chips">
          {urgency && <span className={`chip ${urgency.cls}`}>{urgency.text}</span>}
          {meetingChange && <span className="chip chip-tag">{meetingChange}</span>}
          <span className={`chip ${st.cls}`}>{st.text}</span>
        </div>
      </header>

      <Invitees event={item.event} absentId={item.absentPersonId} people={people}
        extra={invited && <SummariesLink onOpen={() => setShowSummaries(true)} />} />
      {showSummaries && <SummariesDialog itemId={item.id} event={item.event} people={people} me={me} readOnly
        onClose={closeSummaries} />}

      <p className="reason">
        {r.requestedBy === item.absentPersonId
          ? `${name(r.requestedBy)}, who is out, asked you to cover this meeting.`
          : `${name(r.requestedBy)} asked you to cover for ${name(item.absentPersonId)}.`}
        {r.status === "pending" && " Please accept or decline at the earliest."}
        {notesAvailable && " Meeting notes are open to you."}
      </p>

      {r.note && (
        <div className="note">
          <b>Note from {name(r.requestedBy)}:</b>
          <div className="note-text">{r.note}</div>
        </div>
      )}

      {onRespond && r.status === "pending" && (
        <div className="actions">
          <button className="primary" disabled={busy} onClick={() => answer("accepted")}>Accept</button>
          <button disabled={busy} onClick={() => answer("declined")}>Decline</button>
          {busy && <span className="saving" role="status">Saving…</span>}
        </div>
      )}

      {activity.length > 0 && (
        <details className="activity">
          <summary>Activity ({activity.length})</summary>
          <ul>
            {activity.map((h) => (
              <li key={h.id}><span className="activity-when">{fmtWhen(h.at)}</span> {h.text || `${name(h.actorId)}: ${h.detail}`}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}
