/**
 * Plan §5: "The page is fully intact and legible if the decorative layer fails to load
 * entirely. Test this by deliberately breaking the asset path."
 *
 * The hero video is the one asset on this page fetched from a third-party CDN, so it is
 * the only thing that can fail. This aborts every request to it and asserts the page
 * degrades to the self-hosted fallback panel with all copy and CTAs intact.
 *
 *   node scripts/test-hero-fallback.mjs [--url=http://localhost:3000/]
 */
import { chromium } from "@playwright/test";

const url =
  process.argv.find((a) => a.startsWith("--url="))?.slice(6) ?? "http://localhost:3000/";

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  reducedMotion: "reduce",
});
const page = await context.newPage();

let blocked = 0;
await page.route("**/*.mp4", (route) => {
  blocked += 1;
  return route.abort("failed");
});

await page.goto(url, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(1500);

const body = await page.evaluate(() => document.body.innerText);
const videosLeft = await page.locator("video").count();

const checks = {
  "video request was actually blocked": blocked > 0,
  "fallback panel rendered": body.includes("NIT/2026/0412"),
  "headline intact": body.includes("Every bid"),
  "primary CTA intact": body.includes("Get started"),
  "secondary CTA intact": body.includes("Sign in"),
  "broken <video> removed from DOM": videosLeft === 0,
};

for (const [name, pass] of Object.entries(checks)) {
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}`);
}

await browser.close();
process.exit(Object.values(checks).every(Boolean) ? 0 : 1);
