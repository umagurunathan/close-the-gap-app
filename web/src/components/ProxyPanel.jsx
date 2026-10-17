import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { prettyModel } from "./aiBits.jsx";
import { Icon } from "./Icons.jsx";

// Choose a proxy for ONE absent person's item: from the meeting's attendees or anyone in the directory, with an
// optional note (Draft with AI only when allowed). Used on the person's card and on each line of the organizer's card.
export default function ProxyPanel({ item, me, people, onSent, onBack }) {
  const [candidates, setCandidates] = useState([]);
  const [pick, setPick] = useState("");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [note, setNote] = useState("");
  const [fromAi, setFromAi] = useState(false);
  const [draft, setDraft] = useState({ available: false, reason: "" }); // may the note start from an AI draft?
  const [cleared, setCleared] = useState("");
  const [draftSource, setDraftSource] = useState(null); // who wrote the draft: Gemini, or the simple draft
  const [drafting, setDrafting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // the note box fits its text, up to about 20 lines (then it scrolls)
  const noteBox = useRef(null);
  useLayoutEffect(() => {
    const box = noteBox.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight + 2, 460)}px`;
  }, [note]);

  const ev = item.event;
  const ai = item.ai;
  const name = (id) => people[id]?.name ?? id;

  useEffect(() => {
    (async () => {
      try {
        const list = await api(`/items/${item.id}/proxy-candidates`, { person: me });
        setCandidates(list);
        // The first choice is pre-selected, unless someone already declined: then nothing is, it's the person's call.
        const first = list.find((c) => c.choice === "first" && !c.declined);
        setPick(first && !list.some((c) => c.declined) ? first.personId : "");
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [item.id, me, ai.suggestedProxyId]);

  // "Draft with AI" is offered only when the sender AND the chosen proxy can both open the meeting summary, so the
  // note cannot reveal anything the proxy may not read. Asked again whenever the proxy changes; the reason is shown.
  useEffect(() => {
    let current = true;
    (async () => {
      try {
        const q = pick ? `?proxyId=${encodeURIComponent(pick)}` : "";
        const res = await api(`/items/${item.id}/note-draft/available${q}`, { person: me });
        if (!current) return;
        setDraft({ available: res.available, reason: res.reason || "" });
        // An AI draft written for someone else must not go to a proxy who cannot open the summary.
        if (!res.available && fromAi) {
          setNote("");
          setFromAi(false);
          setCleared(`The AI draft was removed. ${res.reason || ""}`.trim());
        }
      } catch (e) {
        if (current) setError(e.message);
      }
    })();
    return () => { current = false; };
    // fromAi is read, not watched: only a change of proxy should trigger this
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id, me, pick]);

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
  const canDraft = draft.available;

  async function draftWithAi() {
    setDrafting(true);
    setError("");
    setCleared("");
    try {
      const res = await api(`/items/${item.id}/note-draft?proxyId=${pick}`, { method: "POST", person: me });
      setNote(res.draft);
      setFromAi(true);
      setDraftSource(res);
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

  // One line says why a button is off: no proxy yet (Send and Draft both wait for one), or why no AI draft is offered.
  const why = !pick ? "Choose a proxy first." : !canDraft && draft.reason ? draft.reason : "";
  const whyId = `proxy-why-${item.id}`;
  const pickReason = pick && candidates.find((c) => c.personId === pick)?.reason;

  // Compact: the two ways to pick side by side, "Draft with AI" beside the note's label, Send with one reason line.
  return (
    <div className="panel proxy-panel">
      <div className="panel-head">
        <h4>Choose a proxy for {name(item.absentPersonId)}</h4>
        <button type="button" className="panel-close" aria-label="Back" title="Back" onClick={onBack}>✕</button>
      </div>
      <div className="pick-row">
        {candidates.length > 0 && (
          <>
            <select value={candidates.some((c) => c.personId === pick) ? pick : ""} onChange={(e) => setPick(e.target.value)}
              aria-describedby={pickReason ? `pick-why-${item.id}` : undefined}>
              <option value="">From this meeting's attendees…</option>
              {candidates.map((c) => (
                <option key={c.personId} value={c.personId}>
                  {name(c.personId)}
                  {(c.choice || c.declined) &&
                    ` (${[c.choice && `${c.choice} choice`, c.declined && "declined"].filter(Boolean).join(", ")})`}
                </option>
              ))}
            </select>
            <span className="pick-or">or</span>
          </>
        )}
        <input type="search" className="pick-search" value={query} aria-label="Search the company directory"
          placeholder="Search the company directory by name or email…" onChange={(e) => searchDirectory(e.target.value)} />
      </div>
      {/* why this person */}
      {pickReason && <p className="pick-why" id={`pick-why-${item.id}`}>{pickReason}</p>}
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
      <div className="note-head">
        <label htmlFor={`note-${item.id}`}>Note for the proxy (optional)</label>
        <span className="note-tools">
          <button type="button" className="small draft-btn" disabled={!canDraft || drafting} onClick={draftWithAi}
            aria-describedby={why ? whyId : undefined}>
            <Icon name="spark" size={13} />{drafting ? "Drafting…" : "Draft with AI"}
          </button>
          {fromAi && draftSource?.engine === "gemini" && (
            <span className="pill src-ai" title="Written by Gemini from the summaries you and the proxy can both open.">
              <Icon name="check" size={13} />Drafted by {prettyModel(draftSource.model)}
            </span>
          )}
          {fromAi && draftSource?.engine === "rules_fallback" && (
            <span className="pill src-rules" title="Gemini did not answer, so a simple draft was made from the summary.">
              Simple draft · AI unavailable
            </span>
          )}
          {fromAi && <span className="reason">Review and edit before sending.</span>}
        </span>
      </div>
      {/* two lines to start; grows to fit the text (an AI brief shows in full, with no empty space under it) */}
      <textarea id={`note-${item.id}`} ref={noteBox} className="note-box" rows={2} value={note}
        placeholder={canDraft ? "Type a note, or use Draft with AI" : "Type your own note for the proxy"}
        onChange={(e) => setNote(e.target.value)} />
      {cleared && <p className="note warn">{cleared}</p>}
      <div className="actions">
        <button className="primary" disabled={busy || !pick} onClick={send} aria-describedby={why ? whyId : undefined}>
          {busy ? "Sending…" : !note.trim() ? "Send proxy request"
            : fromAi && draftSource?.engine === "gemini" ? <><Icon name="spark" size={15} />Send request with the AI note</>
              : "Send request with the note"}
        </button>
        {/* A disabled button always says why: one line for both */}
        {why && <span className="reason" id={whyId}>{why}</span>}
      </div>
      {error && <div className="note warn">{error}</div>}
    </div>
  );
}
