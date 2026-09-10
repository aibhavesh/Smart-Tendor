/**
 * WCAG 2.1 contrast for the theme's colour pairings.
 *
 * Every "passes AA" claim about this theme should come from here rather than from
 * estimation. Phase E's per-screen checklist re-runs it.
 *
 *   node scripts/check-contrast.mjs
 *
 * Exit 1 if any pair marked `required` fails its threshold.
 */

const hex = (h) => {
  const s = h.replace("#", "");
  const n = parseInt(s.length === 3 ? s.split("").map((c) => c + c).join("") : s, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const lin = (c) => {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
};

const luminance = (h) => {
  const [r, g, b] = hex(h).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** Alpha-composite `fg` over `bg` — for the black/60 and /15 tint pairings. */
const over = (fg, bg, alpha) => {
  const f = hex(fg);
  const b = hex(bg);
  const mix = f.map((c, i) => Math.round(c * alpha + b[i] * (1 - alpha)));
  return "#" + mix.map((c) => c.toString(16).padStart(2, "0")).join("");
};

const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const T = {
  canvas: "#e5e4e2",
  ink: "#171717",
  inkStrong: "#000000",
  inkMuted: "#656565",
  brand: "#0084ff",
  brandHover: "#0074e0",
  brandDeep: "#0066cc",
  brandInk: "#005ab5",
  go: "#10b981",
  goDeep: "#059669",
  goInk: "#065f46",
  danger: "#dc2626",
  dangerInk: "#b91c1c",
  violet: "#9333ea",
  violetDeep: "#7e22ce",
  white: "#ffffff",
  surface: "#ffffff",
};

/*
 * Dark theme. Only the entries that actually differ are listed — the brand and
 * state *fills* are shared, so a pairing like "white on brand-deep" is measured
 * once and holds for both. Keep these in step with the html[data-theme="dark"]
 * block in src/app/globals.css.
 */
const D = {
  ...T,
  canvas: "#101214",
  surface: "#1b1f24",
  ink: "#e6e7e9",
  inkStrong: "#ffffff",
  inkMuted: "#9ba1a9",
  brandInk: "#6cb8ff",
  goInk: "#34d399",
  dangerInk: "#f87171",
};

// [label, foreground, background, threshold, required]
// Badges are solid fill + white text — measured, tinted variants sat under AA.
const PAIRS = [
  ["body copy — black/60 on canvas", over(T.inkStrong, T.canvas, 0.6), T.canvas, 4.5, true],
  ["ink on canvas", T.ink, T.canvas, 4.5, true],
  ["ink-muted on canvas", T.inkMuted, T.canvas, 4.5, true],
  ["ink-muted on glass (white/70 over canvas)", T.inkMuted, over(T.white, T.canvas, 0.7), 4.5, true],

  ["white on brand-hover — landing CTA + Button primary", T.white, T.brandHover, 4.5, true],
  ["white on brand-deep — primary hover", T.white, T.brandDeep, 4.5, true],
  ["brand-ink on canvas — landing Sign in + links", T.brandInk, T.canvas, 4.5, true],
  ["brand as decorative icon on canvas (3:1 graphics)", T.brand, T.canvas, 3.0, false],

  ["white on go-ink — VerdictBadge GO", T.white, T.goInk, 4.5, true],
  ["white on brand-deep — VerdictBadge REVIEW", T.white, T.brandDeep, 4.5, true],
  ["white on danger — VerdictBadge NO_BID", T.white, T.danger, 4.5, true],
  ["go-ink on canvas", T.goInk, T.canvas, 4.5, true],
  ["danger-ink on canvas", T.dangerInk, T.canvas, 4.5, true],
  ["ink-muted on canvas — RiskBadge NONE", T.inkMuted, T.canvas, 4.5, true],

  ["white on accent-violet-deep", T.white, T.violetDeep, 4.5, true],

  // --- Dark theme ---------------------------------------------------------
  // The ink ramp is relit against the dark canvas; anything reading as text on
  // it has to be re-measured, because a colour tuned for #e5e4e2 is not legible
  // on #101214. Fills are unchanged and already covered above.
  ["dark: ink on canvas", D.ink, D.canvas, 4.5, true],
  ["dark: ink on surface", D.ink, D.surface, 4.5, true],
  ["dark: ink-muted on canvas", D.inkMuted, D.canvas, 4.5, true],
  ["dark: ink-muted on surface (glass)", D.inkMuted, D.surface, 4.5, true],
  ["dark: body copy — white/60 on canvas", over(D.inkStrong, D.canvas, 0.6), D.canvas, 4.5, true],
  ["dark: brand-ink on canvas — links", D.brandInk, D.canvas, 4.5, true],
  ["dark: go-ink on canvas", D.goInk, D.canvas, 4.5, true],
  ["dark: danger-ink on canvas", D.dangerInk, D.canvas, 4.5, true],
  ["dark: ink-muted on canvas — RiskBadge NONE", D.inkMuted, D.canvas, 4.5, true],
  ["dark: brand as decorative icon on canvas (3:1 graphics)", D.brand, D.canvas, 3.0, false],
];

let failed = 0;
console.log("ratio   need  status  pair");
for (const [label, fg, bg, threshold, required] of PAIRS) {
  const r = contrast(fg, bg);
  const ok = r >= threshold;
  if (!ok && required) failed += 1;
  const status = ok ? "AA  " : required ? "FAIL" : "note";
  console.log(`${r.toFixed(2).padStart(5)}  ${threshold.toFixed(1)}   ${status}    ${label}`);
}

console.log(
  failed
    ? `\n${failed} required pairing(s) below threshold.`
    : "\nAll required pairings meet AA.",
);
process.exit(failed ? 1 : 0);
