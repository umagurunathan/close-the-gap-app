// Small per-browser conveniences (who you're viewing as). Some browsers block site
// storage (privacy settings, private windows), and then any access throws: here that just means "not remembered".
export function remember(key, value) {
  try { localStorage.setItem(key, value); } catch { /* not essential */ }
}

export function recall(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
