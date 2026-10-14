import { fmtWhen } from "../format.js";

// A compact card for a meeting that was rescheduled or cancelled: the gap is closed, nothing is left to do.
// Shows the old time struck through and the new time (or "Cancelled"), and who decided. No buttons.
export default function SettledCard({ title, start, originalStart, status, decidedBy, people }) {
  const name = (id) => people[id]?.name ?? id;
  const cancelled = status === "cancelled";
  return (
    <article className="card settled attn-settled">
      <header className="card-head">
        <div>
          <h3>{title}</h3>
          <div className="when">
            {cancelled ? (
              <><s>{fmtWhen(start)}</s> <span className="moved">Cancelled</span></>
            ) : (
              <>{originalStart && <><s>{fmtWhen(originalStart)}</s> <span aria-hidden="true">→</span> </>}
                <span className="moved">{fmtWhen(start)}</span></>
            )}
          </div>
        </div>
        <div className="chips">
          <span className="chip chip-tag">{cancelled ? "Cancelled" : "Rescheduled"}</span>
        </div>
      </header>
      <div className="note muted">
        {cancelled ? "Cancelled" : "Rescheduled"}{decidedBy ? ` by ${name(decidedBy)}` : ""}. Nothing more to do.
      </div>
    </article>
  );
}
