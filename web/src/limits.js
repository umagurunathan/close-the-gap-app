// The most characters each box takes: the same numbers as [input] in backend/config/settings.toml (the server
// checks them too, with a plain message, so a form that drifts from these can never save too much).
export const LIMITS = { title: 150, agenda: 3000, proxyNote: 2000, summary: 5000 };
