import { fmtWhen } from "../format.js";
import { Icon } from "./Icons.jsx";

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
            <Icon name="calendar" size={14} />
            {cancelled ? (
              <><s>{fmtWhen(start)}</s> <span className="moved">Canceled</span></>
            ) : (
              <>{originalStart && <><s>{fmtWhen(originalStart)}</s> <span aria-hidden="true">→</span> </>}
                <span className="moved">{fmtWhen(start)}</span></>
            )}
          </div>
        </div>
        <div className="chips">
          <span className="chip chip-tag">{cancelled ? "Canceled" : "Rescheduled"}</span>
        </div>
      </header>
      <div className="note muted">
        {cancelled ? "Canceled" : "Rescheduled"}{decidedBy ? ` by ${name(decidedBy)}` : ""}. Nothing more to do.
      </div>
    </article>
  );
}
