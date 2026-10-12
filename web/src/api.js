// All calls to the backend go through here. The shapes are listed at <backend>/docs.
const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function api(path, { method = "GET", body, person } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(person ? { "X-Person-Id": person } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}
