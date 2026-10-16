import { useEffect, useState } from "react";
import { api } from "../api.js";
import { recall, remember } from "../storage.js";

// The impact band: what Close the Gap saved, for a chosen period (rolling windows from the demo's "today").
// Hours are estimates; the formula (from the config) is shown on hover.
const PERIODS = [
  { id: "last", label: "Last week", from: -7, to: -1 },
  { id: "this", label: "This week", from: 0, to: 6 },
  { id: "coming", label: "Coming weeks", from: 7, to: 30 },
  { id: "all", label: "All" },
];

function shift(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function ImpactBand({ today, tick }) {
  const [period, setPeriod] = useState(() => recall("impactPeriod") || "all");
  const [m, setM] = useState(null);

  useEffect(() => {
    const p = PERIODS.find((x) => x.id === period);
    const q = p.from === undefined || !today ? "" : `?start=${shift(today, p.from)}&end=${shift(today, p.to)}`;
    api(`/metrics${q}`).then(setM).catch(() => {});
  }, [period, today, tick]);

  function choose(id) {
    setPeriod(id);
    remember("impactPeriod", id);
  }

  if (!m) return null;

  // One slim row: the counts go in the title line, the four numbers sit beside their labels, the note is one line.
  return (
    <section className="impact-band" aria-label="Impact">
      <div className="impact-head">
        <h2 className="impact-title">
          Company-wide impact
          <small>
            {" "}· {m.absencesSpotted} {m.absencesSpotted === 1 ? "absence" : "absences"} spotted ·{" "}
            {m.meetingsAffected} {m.meetingsAffected === 1 ? "meeting" : "meetings"} affected
          </small>
        </h2>
        <div className="impact-periods" role="group" aria-label="Period">
          {PERIODS.map((p) => (
            <button key={p.id} aria-pressed={period === p.id} onClick={() => choose(p.id)}>{p.label}</button>
          ))}
        </div>
      </div>

      <div className="impact-tiles">
        {/* nothing saved yet in this period (e.g. coming weeks): the honest number is what is at risk */}
        {m.teamHoursSaved > 0 || m.teamHoursAtRisk === 0 ? (
          <div className="impact-tile hero" title={m.estimateNote}>
            <b>{m.teamHoursSaved}<small> h</small></b>
            <span>Team time saved{m.teamHoursAtRisk > 0 && <em>+ {m.teamHoursAtRisk} h still at risk</em>}</span>
          </div>
        ) : (
          <div className="impact-tile hero risk" title={m.estimateNote}>
            <b>{m.teamHoursAtRisk}<small> h</small></b>
            <span>Team time at risk<em>Decide early to save it</em></span>
          </div>
        )}
        <div className="impact-tile" title={`Affected meetings that already have a plan: covered by a proxy, going ahead, rescheduled or canceled by a person, or handled automatically. Of these ${m.meetingsWithPlan}, ${m.handledAutomatically} ${m.handledAutomatically === 1 ? "was" : "were"} handled automatically.`}>
          <b>{m.meetingsWithPlan}<small> of {m.meetingsAffected}</small></b>
          <span>Meetings with the gap closed</span>
        </div>
        <div className="impact-tile" title="On average, how many days before the meeting the plan was made.">
          <b>{m.avgNoticeDays}<small> days</small></b>
          <span>Average notice</span>
        </div>
        <div className="impact-tile" title={m.decisionsCounted
          ? `Of the ${m.decisionsCounted} decisions people made, how many followed the recommendation. Meetings handled automatically are not counted here.`
          : "Counts only decisions made by people. Meetings handled automatically are not counted here."}>
          <b>{m.recommendationsFollowedPct ?? "–"}{m.recommendationsFollowedPct != null && <small>%</small>}</b>
          <span>
            AI recommendations accepted
            {!m.decisionsCounted && (
              <em className="calm">No decisions by people yet{m.handledAutomatically ? ` · ${m.handledAutomatically} handled automatically` : ""}</em>
            )}
          </span>
        </div>
      </div>
      <p className="impact-foot">
        Estimates across everyone's meetings: a leaders' view, open to all in this demo. Hover over a tile to see how it's counted.
      </p>
    </section>
  );
}
