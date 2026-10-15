import { useState } from "react";
import { api } from "../api.js";

// Demo form: the signed-in person schedules a meeting. If a key person (organizer or a required invitee) is already
// out on that day, the backend starts the same flow at once and emails the organizer.
export default function ScheduleMeeting({ people, me, onClose, onDone }) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("2026-10-21");
  const [time, setTime] = useState("10:00");
  const [minutes, setMinutes] = useState(60);
  const [role, setRole] = useState({}); // personId -> "required" | "optional" | ""
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const invitable = Object.values(people).filter((p) => p.id !== me && p.id !== "p_events");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const start = new Date(`${date}T${time}:00`);   // the viewer's own time zone, like every time on screen
      const end = new Date(start.getTime() + Number(minutes) * 60000);
      const attendees = invitable
        .filter((p) => role[p.id])
        .map((p) => ({ personId: p.id, optional: role[p.id] === "optional" }));
      const result = await api("/events", {
        method: "POST", person: me,
        body: { title, start: start.toISOString(), end: end.toISOString(), attendees },
      });
      onDone(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal wide" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Schedule a meeting</h3>
        <label>Title <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Vendor kickoff" required /></label>
        <div className="row">
          <label>Date <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
          <label>Start <input type="time" value={time} onChange={(e) => setTime(e.target.value)} required /></label>
          <label>Minutes <input type="number" min="15" step="15" value={minutes} onChange={(e) => setMinutes(e.target.value)} /></label>
        </div>
        <div className="invite-grid">
          {invitable.map((p) => (
            <label key={p.id} className="invite-row">
              <span>{p.name}</span>
              <select value={role[p.id] || ""} onChange={(e) => setRole({ ...role, [p.id]: e.target.value })}>
                <option value="">Not invited</option>
                <option value="required">Required</option>
                <option value="optional">Optional</option>
              </select>
            </label>
          ))}
        </div>
        <p className="reason">You are the organizer. If a required invitee is already out that day, you will be told straight away.</p>
        {error && <div className="note warn">{error}</div>}
        <div className="actions">
          <button className="primary" type="submit" disabled={busy}>Schedule</button>
          <button type="button" className="link" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
