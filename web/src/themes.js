// Colour themes. The default comes from the config ([ui] theme in backend/config/settings.toml); to try another one,
// add ?theme=google (or blue, clear) to the address. Every colour the page uses is a CSS variable set from here.
// Text colours meet the 4.5:1 contrast minimum on white, except where noted.

const PAGE = (top, mid, bg) => `linear-gradient(180deg, ${top} 0px, ${mid} 220px, ${bg} 420px) no-repeat, ${bg}`;
const GLOW = (rgb, bg) => `radial-gradient(at 50% 0%, rgba(${rgb}, 0.08) 0px, transparent 600px), `
  + `radial-gradient(at 100% 0%, rgba(14, 165, 233, 0.05) 0px, transparent 400px), ${bg}`;

// The blues share everything except the brand colour itself.
const blue = (primary, hover, soft, line, rgb) => ({
  "--primary": primary, "--primary-hover": hover, "--primary-soft": soft, "--primary-rgb": rgb,
  "--bg": "#f8fafc", "--ink": "#1e293b", "--muted": "#64748b", "--line": "#e2e8f0",
  "--good": "#047857", "--good-soft": "#ecfdf5", "--good-text": "#047857", "--warn": "#b45309", "--warn-soft": "#fffbeb",
  "--bad": "#e11d48", "--bad-soft": "#fff1f2",
  "--ai-bg": "#fafcff", "--ai-line": line,
  "--toolbar": "#1e293b", "--toolbar-raise": "#334155", "--toolbar-line": "#475569", "--toolbar-accent": "#93c5fd",
  "--page-bg": GLOW(rgb, "#f8fafc"),
});

export const THEMES = {
  // today's look (the green and amber text are a little under 4.5:1; the blue themes fix that)
  purple: {
    "--primary": "#5b5fc7", "--primary-hover": "#4a4eb3", "--primary-soft": "#e8e9fb", "--primary-rgb": "91, 95, 199",
    "--bg": "#f3f4fa", "--ink": "#232738", "--muted": "#6a7088", "--line": "#e4e6f2",
    "--good": "#2e8b57", "--good-soft": "#e3f4ea", "--good-text": "#18794e", "--warn": "#b26a00", "--warn-soft": "#fff1d6",
    "--bad": "#c4314b", "--bad-soft": "#fde7ec",
    "--ai-bg": "#f6f6fd", "--ai-line": "#ecedf8",
    "--toolbar": "#2b2e45", "--toolbar-raise": "#3a3e5c", "--toolbar-line": "#4c5175", "--toolbar-accent": "#8b8ff0",
    "--page-bg": PAGE("#dfe1f7", "#eceefa", "#f3f4fa"),
  },
  blue: blue("#2563eb", "#1d4ed8", "#eff6ff", "#dbeafe", "37, 99, 235"),
  clear: blue("#2b6fd6", "#235fbb", "#ebf2fc", "#d6e4f8", "43, 111, 214"),
  google: blue("#1a73e8", "#1765cc", "#e8f0fe", "#d2e3fc", "26, 115, 232"),
};

export function applyTheme(name) {
  const theme = THEMES[name] ?? THEMES.purple;
  for (const [key, value] of Object.entries(theme)) document.documentElement.style.setProperty(key, value);
}
