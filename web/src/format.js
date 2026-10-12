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
    cancelled: "Cancelled",
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

// Urgency chip text. `urgency` and `hoursToStart` come from the backend (same for every viewer).
export function urgencyLabel(urgency, hours) {
  if (!urgency) return null;
  if (urgency === "urgent") {
    if (hours <= 0) return "Already started · act now";
    if (hours < 1) return "Starts in under an hour · act now";
    return `Starts in ${Math.round(hours)}h · act now`;
  }
  const days = Math.ceil(hours / 24);
  return days <= 1 ? "Tomorrow" : `In ${days} days`;
}

export function fmtWhen(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "UTC",
  }) + " UTC";
}

export function fmtDay(isoDate) {
  return new Date(isoDate + "T00:00:00Z").toLocaleDateString(undefined, {
    month: "short", day: "numeric", timeZone: "UTC",
  });
}
