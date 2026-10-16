// Small line icons (24×24, drawn with the text colour). Decorative: the text next to them says what they mean.
const PATHS = {
  spark: { fill: true, d: ["M12 2l2.1 6.3L20.5 10l-6.4 2.1L12 18.5l-2.1-6.4L3.5 10l6.4-1.7L12 2Z",
    "M19 15l.9 2.3 2.1.7-2.1.8L19 21l-.9-2.2-2.1-.8 2.1-.7L19 15Z"] },
  check: { d: ["M20 6 9 17l-5-5"] },
  calendar: { d: ["M5.5 5h13a2 2 0 0 1 2 2v11.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z", "M8 3v4M16 3v4M3.5 10h17"] },
  away: { d: ["M5.5 5h13a2 2 0 0 1 2 2v11.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z", "M8 3v4M16 3v4M3.5 10h17",
    "M10 13.5l4 4M14 13.5l-4 4"] },
  info: { d: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z", "M12 11v5", "M12 7.6v.2"] },
  trend: { d: ["M3 17l6-6 4 4 8-8", "M15 7h6v6"] },
  users: { d: ["M9 4.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z", "M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5",
    "M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 14.8c1.6.8 2.7 2.6 3 5.2"] },
  doc: { d: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z", "M14 3v5h5M9 13h6M9 17h4"] },
  shield: { d: ["M12 3 5 6v5.5c0 4.3 2.9 8 7 9.5 4.1-1.5 7-5.2 7-9.5V6l-7-3Z", "m9 12 2 2 4-4"] },
};

export function Icon({ name, size = 16, className = "" }) {
  const icon = PATHS[name];
  return (
    <svg className={`icon ${icon.fill ? "icon-fill" : ""} ${className}`.trim()} width={size} height={size}
      viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {icon.d.map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

// A calm card for a tab with nothing to act on: a green check, a short headline and a line underneath.
export function EmptyState({ title, children }) {
  return (
    <div className="empty-state" role="status">
      <div className="empty-ring"><Icon name="check" size={26} /></div>
      <h4>{title}</h4>
      <p>{children}</p>
    </div>
  );
}
