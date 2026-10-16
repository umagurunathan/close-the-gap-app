// All calls to the backend go through here. The shapes are listed at <backend>/docs.
const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const OFFLINE = "We can't reach the server right now. Please check your connection and try again.";

let authTokenProvider = null;

export function setAuthTokenProvider(provider) {
  authTokenProvider = provider;
}

// Errors carry a message written for people (the server writes them that way); anything technical is replaced here.
// Signed in: the token says who you are, so no demo person is sent. A guest names the demo person they act as.
export async function api(path, { method = "GET", body, person } = {}) {
  let res;
  try {
    const token = authTokenProvider ? await authTokenProvider() : null;
    res = await fetch(BASE + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(!token && person ? { "X-Person-Id": person } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(OFFLINE);
  }
  if (!res.ok) {
    let detail = "";
    let code = "";
    try {
      ({ detail, code = "" } = await res.json());
    } catch {}
    // a list = the request's shape was wrong (a form field missing or invalid); a 5xx = something broke on our side
    if (Array.isArray(detail) || !detail) {
      detail = res.status >= 500
        ? "Something went wrong on our side. Please try again in a moment."
        : "Some details are missing or not valid. Please check and try again.";
    }
    throw Object.assign(new Error(detail), { code });   // e.g. code "not_in_directory"
  }
  return res.json();
}
