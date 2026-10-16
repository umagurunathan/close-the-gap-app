import { useEffect } from "react";

// "Demo guide": whom to pick under "View as" and what to try. Short on purpose; the cards explain the rest.
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
        <p className="reason">
          Pick a person in the dark bar at the top. The people and meetings are sample data; <b>Reset data</b> restores
          them. <b>Emails</b> shows the emails the app would send.
        </p>
        <ol className="guide-steps">
          <li>
            <b>Priya Sharma</b>, going on leave 20–22 Oct. In <b>Attendee Mode</b>, pick a meeting on the left; its
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
            <b>Lena Fox</b>, on vacation for a week (26–30 Oct). A full calendar: daily stand-ups go on without her,
            and each of the other meetings gets its own recommendation.
          </li>
        </ol>
        <p className="reason">
          Each card shows who wrote the recommendation (<b>Gemini · ADK agent</b> or <b>Rule-based</b>) and why.
          A person always decides.
        </p>
      </section>
    </div>
  );
}
