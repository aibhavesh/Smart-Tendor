/**
 * Deterministic page screenshots.
 *
 * Phase B (plan §6.5) has to prove the token refactor changed nothing visually, which
 * means two screenshots that differ only if the styling differs. Animation is therefore
 * frozen rather than merely reduced: `reducedMotion: "reduce"` stops the Framer Motion
 * loops, and the injected stylesheet kills anything CSS-driven that survives it.
 *
 *   node scripts/screenshot.mjs <out.png> [--url=http://localhost:3000/] [--width=1440]
 *                               [--height=900] [--full]
 */
import { chromium } from "@playwright/test";

const [, , outPath, ...rest] = process.argv;

if (!outPath) {
  console.error("usage: node scripts/screenshot.mjs <out.png> [--url=] [--width=] [--height=] [--full]");
  process.exit(1);
}

const flag = (name, fallback) => {
  const hit = rest.find((arg) => arg.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : fallback;
};

const url = flag("url", "http://localhost:3000/");
const width = Number(flag("width", "1440"));
const height = Number(flag("height", "900"));
const fullPage = rest.includes("--full");

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width, height },
  deviceScaleFactor: 2,
  reducedMotion: "reduce",
});
const page = await context.newPage();

// Not "networkidle": Next holds a client connection open, so it never settles.
await page.goto(url, { waitUntil: "load" });
await page.addStyleTag({
  content: `*, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
  }`,
});
await page.evaluate(() => document.fonts.ready);
// Let hydration settle so entrance transforms have landed at their final values.
await page.waitForTimeout(600);

/*
 * Freeze any <video> on a fixed frame. Without this the hero's playing video makes
 * every capture different, which swamps a pixel diff with noise — and, worse, hides
 * real regressions underneath it.
 */
await page.evaluate(async () => {
  const videos = Array.from(document.querySelectorAll("video"));
  await Promise.all(
    videos.map((v) => {
      v.pause();
      if (v.currentTime === 0 && v.readyState >= 2) return Promise.resolve();
      return new Promise((resolve) => {
        v.addEventListener("seeked", resolve, { once: true });
        v.currentTime = 0;
        setTimeout(resolve, 2000);
      });
    }),
  );
});
await page.waitForTimeout(200);

// Surface layout overflow rather than silently cropping it out of the image.
const overflow = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
);
if (overflow > 0) console.warn(`⚠ horizontal overflow: ${overflow}px at ${width}px wide`);

await page.screenshot({ path: outPath, fullPage });
await browser.close();

console.log(`${outPath}  (${width}×${height}${fullPage ? ", full page" : ""})`);
