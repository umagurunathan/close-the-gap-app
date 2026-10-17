import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Icon } from "./Icons.jsx";
import CompanyScale from "./CompanyScale.jsx";

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

// The small (i) next to a number: tap or click to see how it is counted (hover tooltips don't work on touch screens).
function InfoTip({ id, open, onToggle, children }) {
  return (
    <span className="info-wrap">
      <button type="button" className="info-btn" aria-label="How this is counted" aria-expanded={open}
        aria-controls={id} onClick={(e) => { e.stopPropagation(); onToggle(); }}>
        <Icon name="info" size={14} />
      </button>
      {open && <span className="info-pop" id={id} role="note">{children}</span>}
    </span>
  );
}

export default function ImpactBand({ today, tick }) {
  // every page load starts on "All" and open; the period and Hide last only until the page reloads
  const [period, setPeriod] = useState("all");
  const [open, setOpen] = useState(true);
  const [m, setM] = useState(null);
  const [openTip, setOpenTip] = useState(null);   // which tile's "how it's counted" is open
  const [showScale, setShowScale] = useState(false);   // the "At company scale" table

  // a click anywhere else, or Escape, closes it
  useEffect(() => {
    if (!openTip) return undefined;
    const close = () => setOpenTip(null);
    const onKey = (e) => e.key === "Escape" && close();
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", onKey); };
  }, [openTip]);

  useEffect(() => {
    const p = PERIODS.find((x) => x.id === period);
    const q = p.from === undefined || !today ? "" : `?start=${shift(today, p.from)}&end=${shift(today, p.to)}`;
    api(`/metrics${q}`).then(setM).catch(() => {});
  }, [period, today, tick]);

  if (!m) return null;

  const pct = m.meetingsAffected ? Math.round((100 * m.meetingsWithPlan) / m.meetingsAffected) : 0;
  const tips = {
    about: "Estimates across everyone's meetings: a leaders' view, open to all in this demo. Tap the (i) next to a number to see how it is counted.",
    saved: `${m.estimateNote}${m.peopleSpared ? ` ${m.peopleSpared} people were spared a wasted start.` : ""}`,
    gaps: `Affected meetings that already have a plan: covered by a proxy, going ahead, rescheduled or canceled by a person, or handled automatically. Of these ${m.meetingsWithPlan}, ${m.handledAutomatically} ${m.handledAutomatically === 1 ? "was" : "were"} handled automatically.`,
    notice: "On average, how many days before the meeting the plan was made: the earlier, the less disruption.",
    ontime: `Key meetings that went ahead, with a proxy or without the person, instead of waiting for them to come back. Days of waiting avoided: from each meeting to the first working day the person is back${m.decisionsOnSchedule ? ` (${m.daysWaitingAvoided} in all)` : ""}.`,
    accepted: m.decisionsCounted
      ? `Of the ${m.decisionsCounted} decisions people made, how many followed the AI's recommendation. Meetings handled automatically are not counted here.`
      : "Counts only decisions made by people. Meetings handled automatically are not counted here.",
  };
  const tip = (key) => (
    <InfoTip id={`tip-${key}`} open={openTip === key} onToggle={() => setOpenTip(openTip === key ? null : key)}>
      {tips[key]}
    </InfoTip>
  );

  // a chevron only; its tooltip says what it does
  const toggleText = open ? "Hide the company-wide impact" : "Show the company-wide impact";
  const toggle = (
    <button type="button" className="impact-toggle" aria-expanded={open} aria-controls="impact-tiles"
      aria-label={toggleText} title={toggleText} onClick={() => { setOpen(!open); setOpenTip(null); }}>
      <Icon name="chevron" size={16} />
    </button>
  );

  // Hidden: one line with the two headline numbers, so the story stays on screen while the cards get the room.
  if (!open) {
    const label = period === "all" ? "" : ` (${PERIODS.find((p) => p.id === period).label.toLowerCase()})`;
    return (
      <section className="impact-band folded" aria-label="Company-wide impact">
        <div className="impact-head">
          <h2 className="impact-title">
            <Icon name="trend" size={16} />
            Company-wide impact{label}
            <small>
              {" "}· <b>{m.teamHoursSaved} h</b> team time saved · <b>{m.meetingsWithPlan} of {m.meetingsAffected}</b> meetings
              with the gap closed
            </small>
          </h2>
          {toggle}
        </div>
      </section>
    );
  }

  // One slim row: the counts and the note go in the title line, the five numbers sit beside their labels.
  return (
    <section className="impact-band" aria-label="Company-wide impact">
      <div className="impact-head">
        <h2 className="impact-title">
          <Icon name="trend" size={16} />
          Company-wide impact
          <small>
            {" "}· {m.absencesSpotted} {m.absencesSpotted === 1 ? "absence" : "absences"} spotted ·{" "}
            {m.meetingsAffected} {m.meetingsAffected === 1 ? "meeting" : "meetings"} affected · estimates {tip("about")}
          </small>
        </h2>
        <div className="impact-head-tools">
          <div className="impact-periods" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button key={p.id} aria-pressed={period === p.id} onClick={() => setPeriod(p.id)}>{p.label}</button>
            ))}
          </div>
          {toggle}
        </div>
      </div>

      <div className="impact-tiles" id="impact-tiles">
        {/* nothing saved yet in this period (e.g. coming weeks): the honest number is what is at risk */}
        {m.teamHoursSaved > 0 || m.teamHoursAtRisk === 0 ? (
          <div className="impact-tile hero">
            <b>{m.teamHoursSaved}<small> h</small></b>
            <span>Team time saved {tip("saved")}{m.teamHoursAtRisk > 0 && <em>+ {m.teamHoursAtRisk} h still at risk</em>}</span>
          </div>
        ) : (
          <div className="impact-tile hero risk">
            <b>{m.teamHoursAtRisk}<small> h</small></b>
            <span>Team time at risk {tip("saved")}<em>Decide early to save it</em></span>
          </div>
        )}
        <div className="impact-tile">
          <b>{m.decisionsOnSchedule}</b>
          <span>
            Decisions kept on schedule {tip("ontime")}
            {m.decisionsOnSchedule > 0 && <em className="good">{m.daysWaitingAvoided} {m.daysWaitingAvoided === 1 ? "day" : "days"} of waiting avoided</em>}
          </span>
        </div>
        <div className="impact-tile">
          <b>{m.meetingsWithPlan}<small> of {m.meetingsAffected}</small></b>
          <span>
            Meetings with the gap closed {tip("gaps")}
            <span className="impact-bar" role="img" aria-label={`${pct}% of affected meetings have a plan`}>
              <span style={{ width: `${pct}%` }} />
            </span>
          </span>
        </div>
        <div className="impact-tile">
          <b>{m.avgNoticeDays}<small> days</small></b>
          <span>Average notice {tip("notice")}</span>
        </div>
        <div className="impact-tile">
          <b>{m.recommendationsFollowedPct ?? "–"}{m.recommendationsFollowedPct != null && <small>%</small>}</b>
          <span>
            AI recommendations accepted {tip("accepted")}
            {!m.decisionsCounted && (
              <em className="calm">No decisions by people yet{m.handledAutomatically ? ` · ${m.handledAutomatically} handled automatically` : ""}</em>
            )}
          </span>
        </div>
      </div>
      {/* its own line at the bottom-right, as before */}
      <div className="impact-foot">
        <button type="button" className="link scale-link" onClick={() => setShowScale(true)}>At company scale ›</button>
      </div>
      {showScale && <CompanyScale onClose={() => setShowScale(false)} />}
    </section>
  );
}
