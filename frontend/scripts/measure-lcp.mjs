/**
 * Largest Contentful Paint, measured rather than assumed.
 *
 * Plan §5's definition of done includes "LCP is not regressed by the decorative layer".
 * The hero centrepiece is a third-party CDN video, so the question is specifically
 * whether the video becomes the LCP element and drags the metric with it.
 *
 *   node scripts/measure-lcp.mjs [--url=] [--runs=3] [--throttle]
 */
import { chromium } from "@playwright/test";

const arg = (n, d) => process.argv.find((a) => a.startsWith(`--${n}=`))?.slice(n.length + 3) ?? d;
const url = arg("url", "http://localhost:3000/");
const runs = Number(arg("runs", "3"));
const throttle = process.argv.includes("--throttle");

const browser = await chromium.launch();
const results = [];

for (let i = 0; i < runs; i += 1) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  if (throttle) {
    // Roughly "Fast 3G" so the CDN video has to compete for bandwidth.
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 150,
      downloadThroughput: (1.6 * 1024 * 1024) / 8,
      uploadThroughput: (750 * 1024) / 8,
    });
  }

  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(3000);

  // Every candidate, not just the final one — LCP is progressive, and "the video won in
  // the end" is a different fact from "the video blocked the text".
  const entries = await page.evaluate(
    () =>
      new Promise((resolve) => {
        const seen = [];
        // buffered:true replays candidates emitted before this observer existed;
        // getEntriesByType does not surface them.
        new PerformanceObserver((list) => {
          for (const e of list.getEntries()) {
            seen.push({ time: e.startTime, element: e.element?.tagName ?? "?" });
          }
        }).observe({ type: "largest-contentful-paint", buffered: true });
        setTimeout(() => resolve(seen), 400);
      }),
  );

  if (entries.length) results.push(entries);
  await context.close();
}

await browser.close();

if (!results.length) {
  console.log("No LCP entry recorded.");
  process.exit(1);
}

console.log(`network        ${throttle ? "throttled (~1.6 Mbps, 150ms RTT)" : "unthrottled (local)"}`);

const run = results[0];
console.log("LCP candidates in order (first run):");
for (const e of run) {
  console.log(`  ${String(Math.round(e.time)).padStart(5)}ms  <${e.element.toLowerCase()}>`);
}

const finals = results.map((r) => r[r.length - 1].time).sort((a, b) => a - b);
const median = finals[Math.floor(finals.length / 2)];
const finalEl = run[run.length - 1].element.toLowerCase();
const textEntry = run.find((e) => e.element.toLowerCase() !== "video");

console.log(`\nfinal LCP      ${Math.round(median)}ms  <${finalEl}>`);
if (textEntry) {
  console.log(`text painted   ${Math.round(textEntry.time)}ms  <${textEntry.element.toLowerCase()}>`);
}
console.log(
  finalEl === "video"
    ? "\n⚠ The video ends up largest, so it takes the final LCP once it paints."
    : "\n✓ Text is the LCP element; the video never takes it.",
);
