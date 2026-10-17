import { fmtWhen } from "../format.js";
import { Icon } from "./Icons.jsx";

// A compact card for a meeting that was rescheduled or cancelled: the gap is closed, nothing is left to do.
// Shows the old time struck through and the new time (or "Canceled"), and who decided. No buttons.
export default function SettledCard({ title, start, originalStart, status, decidedBy, organizerId, people }) {
  const name = (id) => people[id]?.name ?? id;
  const cancelled = status === "cancelled";
  // "from → to" only when the time really changed (never "6 Nov 8:30 pm → 6 Nov 8:30 pm")
  const moved = originalStart && fmtWhen(originalStart) !== fmtWhen(start);
  const byOrganizer = decidedBy && decidedBy === organizerId;
  const who = decidedBy && decidedBy !== "system" ? `${name(decidedBy)}${byOrganizer ? " (organizer)" : ""}` : null;
  const line = cancelled
    ? `${who ? `${who} canceled it` : "Canceled"}. Nothing more to do.`
    : `${who ? `${who} moved it` : "Moved"} to ${fmtWhen(start)}. Nothing more to do.`;
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
              <>{moved && <><s>{fmtWhen(originalStart)}</s> <span aria-hidden="true">→</span> </>}
                <span className="moved">{fmtWhen(start)}</span></>
            )}
          </div>
        </div>
        <div className="chips">
          <span className="chip chip-tag">
            {cancelled ? "Canceled" : "Rescheduled"}{byOrganizer ? " by organizer" : ""}
          </span>
        </div>
      </header>
      <div className="note muted">{line}</div>
    </article>
  );
}
