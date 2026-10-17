import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icons.jsx";

// "More…" in the Demo controls: a pill like the people beside it that opens a short list of everyone else who has
// something to do. While one of them is viewed, the pill shows their first name, filled like a chosen person.
export default function MorePeople({ people, current, onPick }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const chosen = people.find((p) => p.id === current);
  const none = people.length === 0;

  // a click outside, or Escape, closes it
  useEffect(() => {
    if (!open) return undefined;
    const outside = (e) => { if (!box.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") { setOpen(false); box.current?.querySelector("button")?.focus(); } };
    window.addEventListener("mousedown", outside);
    window.addEventListener("keydown", esc);
    return () => { window.removeEventListener("mousedown", outside); window.removeEventListener("keydown", esc); };
  }, [open]);

  return (
    <span className="more-people" ref={box}>
      <button type="button" className="persona more-btn" aria-haspopup="menu" aria-expanded={open}
        aria-pressed={Boolean(chosen)} disabled={none}
        title={none ? "Nobody else has something to do right now." : "More people to view the app as"}
        onClick={() => setOpen(!open)}>
        <b>{chosen ? chosen.name.split(" ")[0] : "More"}</b>
        <Icon name="chevron" size={13} className="more-chevron" />
      </button>
      {open && (
        <ul className="more-menu" role="menu" aria-label="More people">
          {people.map((p) => (
            <li key={p.id} role="none">
              <button type="button" role="menuitem" aria-current={p.id === current ? "true" : undefined}
                onClick={() => { setOpen(false); onPick(p.id); }}>
                {p.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
