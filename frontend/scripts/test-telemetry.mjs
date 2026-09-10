/**
 * FR-705 frontend log shipping.
 *
 * Three properties matter and none is provable by reading the code:
 *   1. A client-side error actually reaches POST /observability/logs.
 *   2. The batch matches the server's schema (level enum, message bounds, 1..100).
 *   3. A 404 (feature disabled) permanently stops the client instead of retry-storming.
 *
 *   node scripts/test-telemetry.mjs
 */
import { chromium } from "@playwright/test";

const APP = "http://localhost:3000";
const LEVELS = new Set(["debug", "info", "warning", "error"]);

let failures = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  — ${extra}` : ""}`);
};

const browser = await chromium.launch();

// --- 1 & 2: a real error ships, in a schema-valid batch ---------------------
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const posted = [];

  await page.route("**/observability/logs", async (route) => {
    try {
      posted.push(JSON.parse(route.request().postData() ?? "{}"));
    } catch {
      posted.push(null);
    }
    return route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ received: 1 }),
    });
  });

  await page.goto(`${APP}/login`, { waitUntil: "load" });
  await page.waitForTimeout(800);

  // A genuine uncaught error, not a direct call into the logger.
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error("deliberate test failure from e2e");
    }, 0);
  });
  await page.waitForTimeout(1000);
  // `pagehide` flushes unconditionally; a synthetic `visibilitychange` would not,
  // because the handler correctly checks document.visibilityState first.
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await page.waitForTimeout(1200);

  const batches = posted.filter(Boolean);
  check("an uncaught error is shipped", batches.length > 0, `${batches.length} batch(es)`);

  const entries = batches.flatMap((b) => b.logs ?? []);
  check("batch has a `logs` array within 1..100", batches.every((b) => Array.isArray(b.logs) && b.logs.length >= 1 && b.logs.length <= 100));
  check("levels are from the server's enum", entries.every((e) => LEVELS.has(e.level)));
  check("messages are within 2000 chars", entries.every((e) => typeof e.message === "string" && e.message.length >= 1 && e.message.length <= 2000));
  check("entries carry the page URL", entries.every((e) => typeof e.url === "string" && e.url.length > 0));
  check("the thrown message is present", entries.some((e) => e.message.includes("deliberate test failure")));

  await ctx.close();
}

// --- 3: a 404 disables the client permanently -------------------------------
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  let hits = 0;

  await page.route("**/observability/logs", async (route) => {
    hits += 1;
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "log ingestion disabled" }),
    });
  });

  await page.goto(`${APP}/login`, { waitUntil: "load" });
  await page.waitForTimeout(800);

  // Force a first flush, then keep generating errors well past the flush interval.
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error("first error");
    }, 0);
  });
  await page.waitForTimeout(600);
  // `pagehide` flushes unconditionally; a synthetic `visibilitychange` would not,
  // because the handler correctly checks document.visibilityState first.
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await page.waitForTimeout(1000);

  const afterFirst = hits;
  for (let i = 0; i < 5; i += 1) {
    await page.evaluate((n) => {
      setTimeout(() => {
        throw new Error(`later error ${n}`);
      }, 0);
    }, i);
  }
  await page.waitForTimeout(1500);
  // `pagehide` flushes unconditionally; a synthetic `visibilitychange` would not,
  // because the handler correctly checks document.visibilityState first.
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await page.waitForTimeout(1500);

  check("client attempted at least once", afterFirst >= 1, `${afterFirst} request(s)`);
  check(
    "a 404 stops all further attempts",
    hits === afterFirst,
    `${hits} total after ${afterFirst} pre-404`,
  );

  await ctx.close();
}

await browser.close();
console.log(failures ? `\n${failures} telemetry check(s) failed.` : "\nFrontend log shipping behaves correctly.");
process.exit(failures ? 1 : 0);
