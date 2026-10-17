// Labels depend on who is looking: the absent person sees "me/you", everyone else sees the person's name.
export function statusLabel(status, mine, who, chosenAction) {
  const labels = {
    pending_decision: "Not handled yet",
    auto_handled: "Handled automatically",
    attending: mine ? "You'll attend" : `${who} will attend`,
    proceeding_without: mine ? "Going on without you" : `Going on without ${who}`,
    proxy_requested: "Proxy requested",
    proxy_accepted: "Proxy accepted",
    proxy_declined: "Proxy declined",
    awaiting_organizer: chosenAction === "cancel" ? "Cancel requested" : "Reschedule requested",
    rescheduled: "Rescheduled",
    cancelled: "Canceled",
    no_slot_found: "No suitable time found",
  };
  return labels[status] ?? status;
}

export function actionLabel(action, mine, who) {
  switch (action) {
    case "attend": return "I'll attend";
    case "proceed_without": return mine ? "Go on without me" : `Go on without ${who}`;
    case "proxy": return "Proxy";
    case "reschedule": return "Reschedule";
    case "cancel": return "Cancel";
    default: return action;
  }
}

// Days-left chip on every meeting that needs action, on the tile and the card alike: green more than 2 days away,
// amber within 2 days ("soon"), red within 24 hours ("urgent"). `urgency` and `hoursToStart` come from the backend
// (same for every viewer; hoursToStart is set only while the meeting needs action). Returns { cls, text } or null.
export function urgencyChip(urgency, hours) {
  if (hours == null) return null;
  return { cls: `urgency-${urgency || "later"}`, text: urgencyLabel(urgency, hours) };
}

export function urgencyLabel(urgency, hours) {
  if (hours == null) return null;
  if (urgency === "urgent") {
    if (hours <= 0) return "Already started · act now";
    if (hours < 1) return "Starts in under an hour · act now";
    return `Starts in ${Math.round(hours)}h · act now`;
  }
  const days = Math.ceil(hours / 24);
  return days <= 1 ? "Tomorrow" : `In ${days} days`;
}

// ONE date format everywhere, whatever the browser's language: "Tue, 27 Oct · 3:00 pm", in the viewer's own time zone
// (the calendar's way: a meeting at 09:30 UTC shows as 3:00 pm in India).
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fmtTime(d) {
  const h = d.getHours();
  return `${h % 12 || 12}:${String(d.getMinutes()).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
}

export function fmtWhen(iso) {
  const d = new Date(iso);
  return `${WEEKDAY[d.getDay()]}, ${d.getDate()} ${MONTH[d.getMonth()]} · ${fmtTime(d)}`;
}

// A calendar date ("2026-10-27") with no time: "27 Oct". Read as a plain date, so no time zone can shift it.
export function fmtDay(isoDate) {
  const [, m, day] = isoDate.split("-").map(Number);
  return `${day} ${MONTH[m - 1]}`;
}

// "1 meeting is" / "3 meetings are": counts read correctly in English.
// Two calendar dates as one range: "20 – 22 Oct" in the same month, "30 Oct – 2 Nov" across months.
export function fmtRange(startIso, endIso) {
  const [, m1, d1] = startIso.split("-").map(Number);
  const [, m2] = endIso.split("-").map(Number);
  return m1 === m2 ? `${d1} – ${fmtDay(endIso)}` : `${fmtDay(startIso)} – ${fmtDay(endIso)}`;
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

// The tab tag and banner text: "1 needs action", "3 need action".
export function needAction(n) {
  return `${n} ${n === 1 ? "needs" : "need"} action`;
}
