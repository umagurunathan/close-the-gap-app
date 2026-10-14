// Compact invitee list: the people that matter (whoever is out, and the organizer) are always visible; everyone
// else is behind a small expander, so a big meeting doesn't take over the card.
// `absentIds` (several people out, on the organizer's card) or `absentId` (one person's card).
export default function Invitees({ event, absentId, absentIds, people }) {
  const out = new Set(absentIds ?? [absentId]);
  const name = (id) => people[id]?.name ?? id;
  const optional = new Set(event.attendees.filter((a) => a.optional).map((a) => a.personId));
  const all = [event.organizerId, ...event.attendees.map((a) => a.personId)].filter((v, i, arr) => arr.indexOf(v) === i);
  const tag = (id) =>
    [out.has(id) ? "out" : null, id === event.organizerId ? "organizer" : null, optional.has(id) ? "optional" : null]
      .filter(Boolean).join(", ");
  const chip = (id) => (
    <span key={id} className={`person ${out.has(id) ? "out" : ""}`}>
      {name(id)}{tag(id) ? ` (${tag(id)})` : ""}
    </span>
  );
  const key = [...out, event.organizerId].filter((v, i, arr) => arr.indexOf(v) === i);

  return (
    <div className="invitees">
      <div className="people">{key.map(chip)}</div>
      {all.length > key.length && (
        <details className="invitee-list">
          <summary>All invitees ({all.length})</summary>
          <div className="people">{all.map(chip)}</div>
        </details>
      )}
    </div>
  );
}
