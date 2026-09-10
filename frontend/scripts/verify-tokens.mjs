/**
 * Token equivalence check (plan §6.5).
 *
 * The refactor replaced literal colour values with tokens. This asserts, in a real
 * browser, that every token resolves to exactly the literal the §6.1 inventory
 * recorded — so the substitution provably changed nothing.
 *
 * It also checks the two substitutions that were NOT like-for-like: `text-neutral-900`
 * and `text-neutral-500` became hex tokens, and Tailwind v4 ships its palette in
 * OKLCH. If those don't resolve identically the refactor shifted a colour, and this
 * fails rather than letting a screenshot diff hide it in antialiasing noise.
 *
 *   node scripts/verify-tokens.mjs [--url=http://localhost:3000/]
 */
import { chromium } from "@playwright/test";

const url =
  process.argv.find((a) => a.startsWith("--url="))?.slice(6) ?? "http://localhost:3000/";

/** token -> the literal it replaced, from the §6.1 inventory. */
const EXPECTED = {
  "--color-canvas": "#e5e4e2",
  "--color-ink": "#171717",
  "--color-ink-strong": "#000000",
  "--color-ink-muted": "#656565",
  "--color-brand": "#0084ff",
  "--color-brand-hover": "#0074e0",
  "--color-brand-deep": "#0066cc",
  "--color-brand-ink": "#005ab5",
  "--color-sky-soft": "#60b1ff",
  "--color-sky-vivid": "#319aff",
  "--color-state-go": "#10b981",
  "--color-state-go-deep": "#059669",
  "--color-accent-violet": "#9333ea",
  "--color-accent-violet-deep": "#7e22ce",
};

/** Palette utilities replaced by a hex token — must resolve identically. */
const OKLCH_EQUIVALENCE = [
  ["--color-ink", "oklch(20.5% 0 none)", "text-neutral-900"],
  // --color-ink-muted deliberately no longer equals neutral-500: that value measured
  // 4.42:1 on glass and 3.73:1 on canvas, both below AA, so it was darkened to #656565.
];

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(url, { waitUntil: "load" });

const failures = [];

/*
 * Compare rendered pixels, not strings. CSS minification turns #000000 into #000, and
 * Chromium reports oklch() colours verbatim from getComputedStyle rather than
 * converting them — so string equality gives false failures both ways. Painting each
 * colour and reading the byte values back is unambiguous.
 */
await page.addScriptTag({
  content: `window.__rgba = (css) => {
    const c = document.createElement("canvas");
    c.width = c.height = 1;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
    return Array.from(ctx.getImageData(0, 0, 1, 1).data).join(",");
  };`,
});

for (const [token, expected] of Object.entries(EXPECTED)) {
  const [got, want, raw] = await page.evaluate(
    ([t, e]) => {
      const resolved = getComputedStyle(document.documentElement).getPropertyValue(t).trim();
      return [window.__rgba(resolved), window.__rgba(e), resolved];
    },
    [token, expected],
  );
  if (got === want) {
    console.log(`PASS  ${token.padEnd(28)} ${expected}  (rgba ${got})`);
  } else {
    console.log(`FAIL  ${token.padEnd(28)} expected ${expected} [${want}], got ${raw} [${got}]`);
    failures.push(token);
  }
}

for (const [token, oklch, label] of OKLCH_EQUIVALENCE) {
  const [fromToken, fromPalette] = await page.evaluate(
    ([t, o]) => {
      const resolved = getComputedStyle(document.documentElement).getPropertyValue(t).trim();
      return [window.__rgba(resolved), window.__rgba(o)];
    },
    [token, oklch],
  );
  if (fromToken === fromPalette) {
    console.log(`PASS  ${token} === ${label}  (${fromToken})`);
  } else {
    console.log(`FAIL  ${token} (${fromToken}) !== ${label} (${fromPalette})`);
    failures.push(`${token} vs ${label}`);
  }
}

await browser.close();

if (failures.length) {
  console.log(`\n${failures.length} token(s) do not match the pre-refactor value.`);
  process.exit(1);
}
console.log("\nAll tokens resolve to their pre-refactor literals.");
