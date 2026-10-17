import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api.js";
import { fmtWhen } from "../format.js";

// "Summaries & agenda": what the invite says, and the summaries of earlier meetings this person may open (the same
// summaries the AI reads). The organizer can add a summary and choose who reads it (or import one from Google Meet,
// hidden for now, see below).
// A small link on the card opens it, so the card itself stays short. Rendered at the page's top level (a portal).

// Google Meet import is hidden for now: Meet records transcripts only on paid Google Workspace accounts, so with
// personal Gmail accounts there is never a transcript to import. The code stays; set to true to show it again.
const SHOW_MEET_IMPORT = false;

export function SummariesLink({ onOpen }) {
  return <button type="button" className="link summaries-link" onClick={onOpen}>Summaries &amp; agenda</button>;
}

export default function SummariesDialog({ itemId, event, people, me, readOnly = false, refresh, onClose }) {
  const [agenda, setAgenda] = useState(null);
  const [summaries, setSummaries] = useState(null);
  const [meet, setMeet] = useState(null);
  const [text, setText] = useState("");
  const [readers, setReaders] = useState([]);
  const [meetUrl, setMeetUrl] = useState("");
  const [busy, setBusy] = useState("");   // "" | "save" | "link" | "import"
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");   // the confirmation after "Save summary"
  const name = (id) => people[id]?.name ?? id;
  const iAmOrganizer = event.organizerId === me;
  const invitees = [...new Set(event.attendees.map((a) => a.personId).filter((id) => id !== event.organizerId))];

  useEffect(() => {
    Promise.all([
      api(`/items/${itemId}/agenda`, { person: me }),
      api(`/items/${itemId}/notes`, { person: me }),
      SHOW_MEET_IMPORT && iAmOrganizer && !readOnly ? api(`/items/${itemId}/meet`, { person: me }) : Promise.resolve(null),
    ]).then(([a, n, m]) => {
      setAgenda(a.agenda);
      setSummaries(n);
      setMeet(m);
      setMeetUrl(m?.meetUrl || "");
    }).catch((e) => setError(e.message));
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [itemId, me, iAmOrganizer, readOnly, onClose]);

  async function run(kind, call) {
    setBusy(kind);
    setError("");
    try {
      await call();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  const addSummary = (e) => {
    e.preventDefault();
    setSaved("");
    run("save", async () => {
      const note = await api(`/items/${itemId}/notes`, { method: "POST", person: me, body: { text, sharedWith: readers } });
      setSummaries((s) => [...s, note]);
      setText("");
      setReaders([]);
      const who = note.sharedWith.length ? note.sharedWith.map(name).join(", ") : "only you";
      setSaved(`Summary saved. Readable by ${who}. The AI reads it on its next look at this meeting; the card updates by itself.`);
      refresh?.();   // in the background: a new summary can change the AI's recommendation
    });
  };
  const saveMeetLink = (e) => {
    e.preventDefault();
    run("link", async () => {
      const status = await api(`/items/${itemId}/meet`, { method: "PUT", person: me, body: { meetUrl } });
      setMeet(status);
      setMeetUrl(status.meetUrl || "");
    });
  };
  const connectMeet = () => run("link", async () => {
    const { authorizationUrl } = await api("/integrations/google-meet/authorize", { person: me });
    window.location.assign(authorizationUrl);
  });
  const importTranscript = () => run("import", async () => {
    const imported = await api(`/items/${itemId}/meet/import`, { method: "POST", person: me, body: { sharedWith: readers } });
    setSummaries((s) => [...s.filter((x) => x.docId !== imported.docId), imported]);
    await refresh?.();
  });

  const readerPicker = (
    <fieldset className="note-readers">
      <div className="note-readers-head">
        <span>Who can read it</span>
        <button type="button" className="link" onClick={() => setReaders(invitees)}>Select all</button>
      </div>
      {invitees.map((id) => (
        <label className="note-reader" key={id}>
          <input type="checkbox" checked={readers.includes(id)}
            onChange={(e) => setReaders((r) => (e.target.checked ? [...r, id] : r.filter((x) => x !== id)))} />
          {name(id)}
        </label>
      ))}
    </fieldset>
  );

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal summaries" role="dialog" aria-modal="true" aria-labelledby="summaries-title"
        onClick={(e) => e.stopPropagation()}>
        <header className="guide-head">
          <h3 id="summaries-title">{event.title}: summaries &amp; agenda</h3>
          <button className="message-close" onClick={onClose} aria-label="Close" autoFocus>✕</button>
        </header>
        {error && <div className="note warn" role="alert">{error}</div>}
        {summaries === null && !error && <p className="reason">Loading…</p>}
        {summaries !== null && (
          <>
            <h4 className="guide-sub">Agenda</h4>
            <p className="reason">{agenda || "The invite has no agenda."}</p>

            <h4 className="guide-sub">Meeting summaries</h4>
            <p className="reason">
              What earlier meetings discussed and decided. You see only the summaries shared with you; the AI reads the
              same ones.
            </p>
            {summaries.length === 0 ? <p className="reason">No summaries are shared with you yet.</p> : summaries.map((s) => (
              <div className="meeting-note" key={s.docId}>
                <div className="reason">
                  {s.source === "google_meet_transcript" ? "Imported from Google Meet · " : ""}{fmtWhen(s.modifiedAt)}
                </div>
                <p className="note-text">{s.text}</p>
                {iAmOrganizer && (
                  <div className="reason">Shared with: {s.sharedWith.map(name).join(", ") || "only you (organizer)"}</div>
                )}
              </div>
            ))}

            {iAmOrganizer && !readOnly && (
              <>
                <form className="summary-form" onSubmit={addSummary}>
                  <h4 className="guide-sub">Add a summary</h4>
                  {saved && <div className="note good" role="status">{saved}</div>}
                  <textarea rows={4} value={text} onChange={(e) => { setText(e.target.value); setSaved(""); }} required
                    aria-label="Summary text" placeholder="What was discussed and decided, who owns what…" />
                  {readerPicker}
                  <div className="actions">
                    <button className="primary" type="submit" disabled={busy === "save" || !text.trim()}
                      title={!text.trim() ? "Write the summary first." : undefined}>
                      {busy === "save" ? "Saving…" : "Save summary"}
                    </button>
                  </div>
                </form>

                {SHOW_MEET_IMPORT && <details className="meet-capture">
                  <summary>Import a summary from Google Meet</summary>
                  {!meet?.configured ? (
                    <p className="reason">Google Meet isn't set up for this demo.</p>
                  ) : (
                    <>
                      <form className="meet-link-form" onSubmit={saveMeetLink}>
                        <label className="note-label">
                          Meet link
                          <input type="url" value={meetUrl} onChange={(e) => setMeetUrl(e.target.value)}
                            placeholder="https://meet.google.com/abc-defg-hij" required />
                        </label>
                        <button type="submit" disabled={busy === "link" || !meetUrl.trim()}
                          title={!meetUrl.trim() ? "Paste the meeting's Google Meet link first." : undefined}>
                          {busy === "link" ? "Saving…" : "Save Meet link"}
                        </button>
                      </form>
                      <div className="actions">
                        <button onClick={connectMeet}>{meet.connected ? "Reconnect Google Meet" : "Connect Google Meet"}</button>
                      </div>
                      {meet.connected && meet.meetUrl && (
                        <>
                          <p className="reason">After the call, once Google Meet has the transcript, import it as a summary.</p>
                          {readerPicker}
                          <button disabled={busy === "import"} onClick={importTranscript}>
                            {busy === "import" ? "Importing…" : "Import transcript"}
                          </button>
                        </>
                      )}
                    </>
                  )}
                </details>}
              </>
            )}
          </>
        )}
      </section>
    </div>,
    document.body,
  );
}
