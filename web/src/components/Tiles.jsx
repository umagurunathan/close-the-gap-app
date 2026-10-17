import { actionLabel, fmtWhen, statusLabel, urgencyChip } from "../format.js";
import { Icon } from "./Icons.jsx";

// The small tiles on the left of each tab: title, time, and one line saying where the meeting stands.
// The full card on the right says everything else.

const first = (people, id) => (people[id]?.name ?? id ?? "").split(" ")[0];
const CONF = { high: "High", medium: "Medium", low: "Low" };

function Frame({ title, start, edge, chip, children }) {
  return (
    <span className={`tile attn-${edge}`}>
      <span className="tile-head">
        <span className="tile-title">{title}</span>
        {chip && <span className={`chip ${chip.cls}`}>{chip.text}</span>}
      </span>
      <span className="tile-when"><Icon name="calendar" size={13} />{fmtWhen(start)}</span>
      <span className="tile-line">{children}</span>
    </span>
  );
}

// Attendee Mode: one tile per meeting the signed-in person is out for.
export function AttendeeTile({ item, people, me }) {
  const ai = item.ai;
  const mine = item.absentPersonId === me;
  const who = first(people, item.absentPersonId);
  const edge = item.needsAttention ? (item.urgency || "open") : item.status === "auto_handled" ? "quiet" : "settled";
  let line;
  if (item.status === "pending_decision") {
    line = ai.engine === "analysing" ? <span className="muted">AI analyzing…</span> : (
      <>
        <b>{ai.recommendation ? actionLabel(ai.recommendation, mine, who) : "Your choice is needed"}</b>
        {ai.recommendation === "proxy" && ai.suggestedProxyId && <> → <span className="proxy-name">{people[ai.suggestedProxyId]?.name}</span></>}
        {ai.recommendation && <span className={`pill conf-${ai.confidence}`}>{CONF[ai.confidence]}</span>}
      </>
    );
  } else if (item.status === "proxy_requested") {
    line = <>Waiting for {first(people, item.chosenProxyId)} to answer</>;
  } else if (item.status === "proxy_declined") {
    const declined = item.declinedProxyIds || [];
    line = <>{first(people, declined.at(-1))} declined · choose again</>;
  } else if (item.status === "proxy_accepted") {
    line = <span className="done-line"><Icon name="check" size={14} />{first(people, item.chosenProxyId)} will cover</span>;
  } else if (item.status === "auto_handled") {
    line = <>{item.kind === "org_event" ? "Org-wide event" : "Team check-in"} · going on without {mine ? "you" : who}</>;
  } else if (item.needsAttention) {
    line = <>{statusLabel(item.status, mine, who, item.chosenAction)}</>;
  } else {
    line = <span className="done-line"><Icon name="check" size={14} />{statusLabel(item.status, mine, who, item.chosenAction)}</span>;
  }
  return (
    <Frame title={item.event.title} start={item.event.start} edge={edge}
      chip={item.needsAttention ? urgencyChip(item.urgency, item.hoursToStart) : null}>
      {line}
    </Frame>
  );
}

// Organizer Mode: one tile per meeting, naming who is out.
const MEETING_LABEL = { reschedule: "Reschedule", proceed_without: "Go on without them", cancel: "Cancel", proxy: "Arrange a proxy" };
export function OrganizerTile({ meeting, people }) {
  const names = meeting.absentees.map((a) => first(people, a.absentPersonId));
  const out = names.length <= 2 ? names.join(" and ") : `${names.slice(0, 2).join(", ")} +${names.length - 2}`;
  const status = meeting.absentees[0]?.status;
  const edge = meeting.done ? "settled" : meeting.needsAttention ? (meeting.urgency || "open") : "settled";
  const line = meeting.done
    ? <span className="done-line"><Icon name="check" size={14} />{statusLabel(status, false, "", null)}</span>
    : meeting.needsAttention
      ? <>{out} out · <b>{meeting.ai.recommendation ? MEETING_LABEL[meeting.ai.recommendation] : "Your choice is needed"}</b></>
      : <span className="done-line"><Icon name="check" size={14} />{out} out · settled</span>;
  return (
    <Frame title={meeting.event.title} start={meeting.event.start} edge={edge}
      chip={meeting.needsAttention ? urgencyChip(meeting.urgency, meeting.hoursToStart) : null}>
      {line}
    </Frame>
  );
}

// Proxy Requests: one tile per request to cover a meeting.
export function ProxyTile({ view, people }) {
  const { request: r, item } = view;
  const forWho = people[item.absentPersonId]?.name ?? "";
  const line = r.status === "pending" ? <>For {forWho} · <b>waiting for your answer</b></>
    : r.status === "accepted" ? <span className="done-line"><Icon name="check" size={14} />You're covering for {first(people, item.absentPersonId)}</span>
      : r.status === "declined" ? <>You declined · for {forWho}</> : <>No longer needed · for {forWho}</>;
  return (
    <Frame title={item.event.title} start={item.event.start} edge={r.status === "pending" ? (item.urgency || "open") : "settled"}
      chip={r.status === "pending" ? urgencyChip(item.urgency, item.hoursToStart) : null}>
      {line}
    </Frame>
  );
}
