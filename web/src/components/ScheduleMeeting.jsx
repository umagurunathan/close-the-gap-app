import { useState } from "react";
import { api } from "../api.js";

// Schedule a meeting. Invitees: type a name, pick from the matches, and each person becomes a chip; click a chip's
// role to switch Required / Optional, ✕ to remove. If a required invitee is already out that day, the organizer is
// told straight away (the backend checks).
export default function ScheduleMeeting({ people, me, today, onClose, onDone }) {
  const [title, setTitle] = useState("");
  const [agenda, setAgenda] = useState("");   // the invite body: agenda, plan, notes (the AI reads it)
  const [date, setDate] = useState(today ? addDays(today, 10) : "2026-10-21");
  const [time, setTime] = useState("10:00");
  const [minutes, setMinutes] = useState(60);
  const [invited, setInvited] = useState([]);   // [{ personId, optional }]
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const name = (id) => people[id]?.name ?? id;
  const chosen = new Set(invited.map((i) => i.personId));
  const q = query.trim().toLowerCase();
  const matches = q.length < 1 ? [] : Object.values(people)
    .filter((p) => !p.isGroup && p.id !== me && !chosen.has(p.id)
      && (p.name.toLowerCase().includes(q) || p.email.toLowerCase().includes(q) || (p.title || "").toLowerCase().includes(q)))
    .slice(0, 6);

  const add = (id) => { setInvited([...invited, { personId: id, optional: false }]); setQuery(""); };
  const toggle = (id) => setInvited(invited.map((i) => (i.personId === id ? { ...i, optional: !i.optional } : i)));
  const remove = (id) => setInvited(invited.filter((i) => i.personId !== id));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const start = new Date(`${date}T${time}:00`);   // the viewer's own time zone, like every time on screen
      const end = new Date(start.getTime() + Number(minutes) * 60000);
      const result = await api("/events", {
        method: "POST", person: me,
        body: { title, description: agenda, start: start.toISOString(), end: end.toISOString(), attendees: invited },
      });
      onDone(result, start.toISOString());
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
        <label><span>Agenda / notes <span className="optional-tag">(optional)</span></span>
          <textarea rows={3} value={agenda} onChange={(e) => setAgenda(e.target.value)}
            placeholder="What is this meeting for? Agenda, plan, decisions needed, who presents what…" />
        </label>
        <div className="row">
          <label>Date <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
          <label>Start <input type="time" value={time} onChange={(e) => setTime(e.target.value)} required /></label>
          <label>Duration (minutes) <input type="number" min="15" step="15" value={minutes} onChange={(e) => setMinutes(e.target.value)} /></label>
        </div>

        <label>Invite people
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a name, email or role…" aria-describedby="invite-help"
            onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) { e.preventDefault(); add(matches[0].id); } }} />
        </label>
        {matches.length > 0 && (
          <ul className="invite-matches" role="listbox" aria-label="Matching people">
            {matches.map((p) => (
              <li key={p.id}>
                <button type="button" onClick={() => add(p.id)}>
                  <b>{p.name}</b> <span className="reason">· {p.title}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {invited.length > 0 ? (
          <div className="invite-chips" aria-label="Invited">
            {invited.map((i) => (
              <span key={i.personId} className={`invite-chip ${i.optional ? "optional" : ""}`}>
                {name(i.personId)}
                <button type="button" className="chip-role" onClick={() => toggle(i.personId)}
                  title="Click to switch between required and optional">
                  {i.optional ? "Optional" : "Required"}
                </button>
                <button type="button" className="chip-remove" onClick={() => remove(i.personId)}
                  aria-label={`Remove ${name(i.personId)}`}>✕</button>
              </span>
            ))}
          </div>
        ) : (
          <p className="reason" id="invite-help">Nobody invited yet. Type a name above and press Enter or click a match.</p>
        )}

        <p className="reason">You are the organizer. If a required invitee is already out that day, you will be told straight away.</p>
        {error && <div className="note warn">{error}</div>}
        <div className="actions">
          <button className="primary" type="submit" disabled={busy}>{busy ? "Scheduling…" : "Schedule"}</button>
          <button type="button" className="link" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}

function addDays(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
