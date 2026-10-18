import { useEffect } from "react";
import { Icon } from "./Icons.jsx";

// "Demo guide": the main story as four steps in a row, the rule about
// which meetings are listed first and plainly, a few more people to try, and the full text behind "Detailed
// instructions". Pure explanation: nothing here changes who is viewed (pick each person under View as).
const STORY = [
  { who: "Priya", role: "is going on leave",
    where: "Attendee Mode", steps: [<>Open <b>Q4 Budget Review</b></>, <><b>Ask Meena to cover</b></>, <><b>Draft with AI</b>, then <b>Send</b></>] },
  { who: "Meena", role: "is asked to cover",
    where: "Proxy Requests", steps: [<><b>Accept</b> the request</>, <>Priya's card moves to <b>Settled</b> ✓</>] },
  { who: "Sam", role: "organizes the meetings",
    where: "Organizer Mode", steps: [<>One card per meeting, with <b>everyone who is out</b></>, <>Decide for the <b>whole meeting</b></>] },
  { who: "Arjun", role: "where the AI beats rules",
    where: "Attendee Mode", steps: [<>Open <b>Weekly Ops Sync</b></>, <><b>AI changed the answer</b>: what simple rules said vs Gemini</>] },
];

const ALSO = [
  ["Kiran", "out suddenly"],
  ["Lena", "a week off"],
  ["Dev", "declines a request"],
  ["Ben", "an organizer outside the team"],
];

export default function DemoGuide({ onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal guide" role="dialog" aria-modal="true" aria-labelledby="guide-title"
        onClick={(e) => e.stopPropagation()}>
        <header className="guide-head">
          <h3 id="guide-title">Demo guide</h3>
          <button className="message-close" onClick={onClose} aria-label="Close the demo guide" autoFocus>✕</button>
        </header>

        <div className="guide-rule" role="note">
          <span className="guide-rule-icon" aria-hidden="true">i</span>
          <div>
            <b>Close the Gap lists only meetings affected by someone's absence.</b>
            <div>A meeting with no conflict stays in the calendar and does not appear here.</div>
          </div>
        </div>

        <div className="guide-rule" role="note">
          <span className="guide-rule-icon" aria-hidden="true">i</span>
          <div>
            <b>Want to try your own scenario?</b>
            <div>
              The sample people and meetings are just here to get you started. The <b>Report an absence</b> feature lets
              you add your own leave, and the <b>Schedule a meeting</b> feature lets you add your own meeting. Either one
              takes you through the full flow, from the AI's recommendation to the final decision.
            </div>
          </div>
        </div>

        <h4 className="guide-story-title">The main story: pick each person under <b>View as</b>, in order</h4>
        <ol className="guide-flow">
          {STORY.map((s, n) => (
            <li key={s.who} className="guide-step">
              <div className="guide-step-head">
                <span className="guide-num" aria-hidden="true">{n + 1}</span>
                <div>
                  <div className="guide-who">{s.who}</div>
                  <div className="guide-role">{s.role}</div>
                </div>
              </div>
              <div className="guide-where">{s.where}</div>
              <ul className="guide-do">
                {s.steps.map((t, k) => <li key={k}>{t}</li>)}
              </ul>
              {n < STORY.length - 1 && <span className="guide-arrow" aria-hidden="true">›</span>}
            </li>
          ))}
        </ol>

        <div className="guide-also">
          <span className="guide-also-label">Also try</span>
          {ALSO.map(([who, what]) => (
            <span key={who} className="guide-chip"><b>{who}</b> · {what}</span>
          ))}
        </div>

        <div className="guide-foot">
          <span><Icon name="spark" size={13} /> Each card says who wrote the recommendation and why. A person always decides.</span>
          <span><b>Reset demo data</b> starts the story over for everyone.</span>
        </div>

        <details className="guide-details">
          <summary>Detailed instructions</summary>
          <p className="reason">
            Pick a person under <b>View as</b> in the Demo controls at the top. <b>Emails</b> shows the emails the app
            would send. Anyone else appears under <b>More…</b> only while they have something to do, for example a proxy
            request to answer. The people below are only a suggested path. At any time you can use <b>Report an
            absence</b> or <b>Schedule a meeting</b> to add your own, and follow it from the recommendation to the proxy
            request to the decision.
          </p>
          <ol className="guide-steps">
            <li>
              <b>Priya Sharma</b>, going on leave 17–19 Nov. In <b>Attendee Mode</b>, pick a meeting on the left; its
              AI recommendation opens on the right. On <b>Q4 Budget Review</b>, try <b>Ask Meena to cover</b> →
              <b> Draft with AI</b> for a handover note. Decided meetings move to <b>Settled</b>; team check-ins wait in
              <b> No action needed</b>.
            </li>
            <li>
              <b>Meena Iyer</b>, asked to cover. In <b>Proxy Requests</b>, <b>Accept</b> or <b>Decline</b>. If she
              declines, Priya's card offers the second choice.
            </li>
            <li>
              <b>Sam Wilson</b>, organizer. In <b>Organizer Mode</b>, one card per meeting with everyone who is out; he can
              act for the whole meeting.
            </li>
            <li>
              <b>Arjun Rao</b>, where the AI beats simple rules. His cards show the agent's steps and what simple rules
              alone would have said. "Weekly Ops Sync" looks routine, but the AI flags it.
            </li>
            <li>
              <b>Kiran Patel</b>, out suddenly. His organizer, Sam, is alerted straight away.
            </li>
            <li>
              <b>Lena Fox</b>, on vacation for a week (23–27 Nov). A full calendar: daily stand-ups go on without her,
              and each of the other meetings gets its own recommendation.
            </li>
            <li>
              <b>Dev Nair</b>, a proxy who says no. As Priya, ask Dev to cover <b>Sprint Planning</b>; as Dev,
              <b> Decline</b> in <b>Proxy Requests</b>. Priya's card then offers <b>Choose another proxy</b>.
            </li>
            <li>
              <b>Ben Carter</b>, Legal Counsel, organizer of <b>Audit Committee Prep</b>, which Arjun will miss. In
              <b> Organizer Mode</b>, his card suggests who can cover for Arjun.
            </li>
          </ol>
          <p className="reason">
            The eight people above are the demo people; their colleagues in the same meetings are sample data too.
            <b> Reset demo data</b> puts all of their meetings, requests and decisions back to the start and lets the AI
            analyze every card again. Real users who sign in with Google are never touched.
          </p>
        </details>
      </section>
    </div>
  );
}
