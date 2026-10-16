// The Close the Gap mark: two calendar halves, and the bar that closes the gap between them.
// The same drawing is the browser-tab icon (web/public/favicon.svg).
export default function Logo({ size = 40 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      {/* the brand colour follows the theme (web/src/themes.js) */}
      <rect x="1" y="1" width="38" height="38" rx="11" style={{ fill: "var(--primary)" }} />
      {/* left calendar half */}
      <rect x="7" y="11" width="11" height="19" rx="3" fill="#ffffff" />
      <rect x="9.5" y="8" width="2.4" height="5" rx="1.2" fill="#ffffff" />
      {/* right calendar half */}
      <rect x="22" y="11" width="11" height="19" rx="3" fill="#ffffff" fillOpacity="0.72" />
      <rect x="28.1" y="8" width="2.4" height="5" rx="1.2" fill="#ffffff" fillOpacity="0.72" />
      {/* the bar closing the gap */}
      <rect x="14.5" y="18.5" width="11" height="4.5" rx="2.25" fill="#34c38f" />
    </svg>
  );
}
