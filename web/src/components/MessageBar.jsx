import { useEffect } from "react";

// One message at the top of the page. Errors stay until closed (so nobody misses one); other messages close by
// themselves after a few seconds (`hideAfter`, from the backend's config file).
const ICON = { error: "⚠", success: "✓", info: "ℹ" };

// `action` (optional): { label, onClick }, a button inside the message, e.g. "Open Sam's view".
export default function MessageBar({ kind = "info", text, onClose, hideAfter = 6, action = null }) {
  useEffect(() => {
    if (!text || kind === "error" || !hideAfter) return undefined;
    // a long message gets twice the time to read
    const timer = setTimeout(onClose, hideAfter * (text.length > 100 ? 2 : 1) * 1000);
    return () => clearTimeout(timer);
  }, [text, kind, hideAfter, onClose]);

  if (!text) return null;
  return (
    <div className={`message message-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <span className="message-icon" aria-hidden="true">{ICON[kind]}</span>
      <span className="message-text">{text}</span>
      {action && <button className="message-action" onClick={() => { action.onClick(); onClose(); }}>{action.label}</button>}
      <button className="message-close" onClick={onClose} aria-label="Close this message">✕</button>
    </div>
  );
}
