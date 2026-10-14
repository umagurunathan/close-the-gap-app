import { useEffect, useState } from "react";
import { api } from "../api.js";

// Choose a proxy for ONE absent person's item: from the meeting's attendees or anyone in the directory, with an
// optional note (Draft with AI only when allowed). Used on the person's card and on each line of the organizer's card.
export default function ProxyPanel({ item, me, people, onSent, onBack }) {
  const [candidates, setCandidates] = useState([]);
  const [pick, setPick] = useState("");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [note, setNote] = useState("");
  const [fromAi, setFromAi] = useState(false);
  const [draftOk, setDraftOk] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ev = item.event;
  const ai = item.ai;
  const name = (id) => people[id]?.name ?? id;

  useEffect(() => {
    (async () => {
      try {
        const list = await api(`/items/${item.id}/proxy-candidates`, { person: me });
        setCandidates(list);
        setPick(ai.suggestedProxyId && list.some((c) => c.personId === ai.suggestedProxyId) ? ai.suggestedProxyId : "");
        // "Draft with AI" is offered only when the host shared the summary with everyone invited
        setDraftOk((await api(`/items/${item.id}/note-draft/available`, { person: me })).available);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [item.id, me, ai.suggestedProxyId]);

  // Anyone in the company directory can be named, invited or not. The search runs on the server.
  async function searchDirectory(text) {
    setQuery(text);
    if (text.trim().length < 2) return setMatches([]);
    try {
      const day = ev.start.slice(0, 10); // so people on leave that day are flagged
      const found = await api(`/directory?q=${encodeURIComponent(text.trim())}&day=${day}`, { person: me });
      setMatches(found.filter((p) => p.id !== item.absentPersonId));
    } catch (e) {
      setError(e.message);
    }
  }

  const invitedIds = new Set([ev.organizerId, ...ev.attendees.map((a) => a.personId)]);
  const pickedOutsider = pick && !invitedIds.has(pick);
  // An AI draft is built from summaries shared with everyone invited, so it is off for someone who is not invited.
  const canDraft = draftOk && !pickedOutsider;
  // If an AI draft was already written and the sender then picks someone not invited, drop it.
  useEffect(() => {
    if (pickedOutsider && fromAi) {
      setNote("");
      setFromAi(false);
    }
  }, [pickedOutsider, fromAi]);

  async function draftWithAi() {
    setDrafting(true);
    setError("");
    try {
      const { draft } = await api(`/items/${item.id}/note-draft?proxyId=${pick}`, { method: "POST", person: me });
      setNote(draft);
      setFromAi(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setDrafting(false);
    }
  }

  async function send() {
    setBusy(true);
    setError("");
    try {
      await api(`/items/${item.id}/action`, {
        method: "POST", person: me, body: { action: "proxy", proxyId: pick, note, noteFromAi: fromAi },
      });
      await onSent();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h4>Choose a proxy for {name(item.absentPersonId)}</h4>
      {candidates.length > 0 && (
        <>
          <select value={candidates.some((c) => c.personId === pick) ? pick : ""} onChange={(e) => setPick(e.target.value)}>
            <option value="">From this meeting's attendees…</option>
            {candidates.map((c) => (
              <option key={c.personId} value={c.personId}>
                {name(c.personId)}{c.personId === ai.suggestedProxyId ? " (suggested)" : ""}
              </option>
            ))}
          </select>
          {pick && candidates.some((c) => c.personId === pick) && (
            <p className="reason">{candidates.find((c) => c.personId === pick)?.reason}</p>
          )}
        </>
      )}
      <input type="search" value={query} placeholder="Or search the company directory by email…"
        onChange={(e) => searchDirectory(e.target.value)} />
      {matches.length > 0 && (
        <select value={matches.some((p) => p.id === pick) ? pick : ""} onChange={(e) => setPick(e.target.value)}>
          <option value="">Select from the directory…</option>
          {matches.map((p) => (
            <option key={p.id} value={p.id} disabled={p.out}>
              {p.email} · {p.name} · {p.title}{p.out ? " (out of office that day)" : invitedIds.has(p.id) ? "" : " (not invited)"}
            </option>
          ))}
        </select>
      )}
      {pickedOutsider && (
        <p className="reason">{name(pick)} isn't on this invite. They'll be added as an optional attendee when you send the request.</p>
      )}
      <label className="note-label">
        Note for the proxy (optional)
        <textarea rows={4} value={note}
          placeholder={canDraft ? "Type a note, or use Draft with AI" : "Type your own note for the proxy"}
          onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="actions">
        <button disabled={!canDraft || drafting} onClick={draftWithAi}>{drafting ? "Drafting…" : "Draft with AI"}</button>
        {fromAi && <span className="reason">Review and edit before sending.</span>}
      </div>
      <div className="actions">
        <button className="primary" disabled={busy || !pick} onClick={send}>Send proxy request</button>
        <button className="link" onClick={onBack}>Back</button>
      </div>
      {error && <div className="note warn">{error}</div>}
    </div>
  );
}
