/**
 * Drives a tender through the whole lifecycle using only the UI.
 *
 *   REGISTERED --upload--> DOWNLOADED --extract--> PARSED --analyse--> ANALYZED --review--> REVIEWED
 *
 * This is the path that was unreachable before the ingestion UI existed, which is why the
 * analysed screens had only ever been exercised against fixtures. Everything here goes
 * through real controls against the real backend — no API calls from the test.
 *
 * Requires the app on :3000, a seeded backend on :8000, and the generated test PDF.
 *
 *   node scripts/e2e-lifecycle.mjs
 */
import { chromium } from "@playwright/test";

const APP = "http://localhost:3000";
const PDF = "C:/Users/dever/AppData/Local/Temp/nit-2026-0398.pdf";
const TENDER = process.argv.find((a) => a.startsWith("--tender="))?.slice(9) ?? "NIT/2026/0398";
const ANALYST = { email: "analyst@example.com", password: "password123" };
const MANAGER = { email: "manager@example.com", password: "password123" };

let failures = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  — ${extra}` : ""}`);
};

const browser = await chromium.launch();

async function signIn(page, who) {
  await page.goto(`${APP}/login`, { waitUntil: "load" });
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard", { timeout: 15000 }).catch(() => {});
}

// ---------------------------------------------------------------- analyst
const analystCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await analystCtx.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));

await signIn(page, ANALYST);

// Find the reservoir tender and open it.
await page.goto(`${APP}/tenders`, { waitUntil: "load" });
await page.waitForTimeout(1200);
await page.getByRole("link", { name: TENDER }).click();
await page.waitForTimeout(1500);
const tenderUrl = page.url();
let body = await page.evaluate(() => document.body.innerText);
check("starts at REGISTERED", body.includes("REGISTERED"));
check("extract is blocked with a reason", body.includes("Add a document first"));

// --- upload -> DOWNLOADED -------------------------------------------------
await page.setInputFiles('input[type="file"]', PDF);
await page.waitForTimeout(3500);
body = await page.evaluate(() => document.body.innerText);
check("upload succeeds and says so", body.includes("Uploaded"));
check("document listed as DOWNLOADED", body.includes("DOWNLOADED"));
check("tender advanced to DOWNLOADED", /\bDOWNLOADED\b/.test(body));

// --- extract -> PARSED ----------------------------------------------------
await page.getByRole("button", { name: /Extract/ }).click();
await page.waitForTimeout(6000);
body = await page.evaluate(() => document.body.innerText);
check("tender advanced to PARSED", body.includes("PARSED"));
check("extracted metadata now rendered", !body.includes("Nothing extracted yet"));
check("a confidence score is shown", /0\.\d{2}/.test(body));

// --- analyse -> ANALYZED --------------------------------------------------
await page.getByRole("button", { name: /Run analysis/ }).click();
await page.waitForTimeout(8000);
body = await page.evaluate(() => document.body.innerText);
check("tender advanced to ANALYZED", body.includes("ANALYZED"));
check("a verdict is rendered", /\b(GO|REVIEW|NO BID)\b/.test(body));
check("the rule trail is shown", body.includes("RULES THAT PRODUCED THIS VERDICT"));
check("risk section populated", body.includes("Risk") && /\d\.\d \/ 10/.test(body));
check("qualification section populated", body.includes("Qualification"));

await page.screenshot({ path: "C:/Users/dever/AppData/Local/Temp/shots/lifecycle-analysed.png", fullPage: true });
await analystCtx.close();

// ---------------------------------------------------------------- manager
const managerCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const mgr = await managerCtx.newPage();
mgr.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));

await signIn(mgr, MANAGER);
await mgr.goto(`${APP}/reviews`, { waitUntil: "load" });
await mgr.waitForTimeout(1600);
let mbody = await mgr.evaluate(() => document.body.innerText);
check("analysed tender appears in the review queue", mbody.includes(TENDER));

await mgr.getByRole("button", { name: "Review" }).first().click();
await mgr.waitForTimeout(900);

// A correction is what produces a before/after snapshot — §8 calls that the point of
// the review record, so a review with no corrections would not exercise it at all.
await mgr.getByRole("button", { name: /Add a correction/ }).click();
await mgr.waitForTimeout(400);
await mgr.getByLabel("Field").fill("department");
await mgr.getByLabel("Corrected value").fill("Water Resources Division (North)");
await mgr.getByRole("button", { name: /Record review/ }).click();
await mgr.waitForTimeout(3500);
mbody = await mgr.evaluate(() => document.body.innerText);
check("review recorded", mbody.includes("Recorded as"));
check(
  "before/after snapshot rendered side by side",
  mbody.includes("Original") && mbody.includes("Corrected"),
);
check("the corrected value appears", mbody.includes("Water Resources Division (North)"));

await mgr.goto(`${tenderUrl}`, { waitUntil: "load" });
await mgr.waitForTimeout(1800);
mbody = await mgr.evaluate(() => document.body.innerText);
check("tender advanced to REVIEWED", mbody.includes("REVIEWED"));
check("review history now shown", mbody.includes("Review history"));

await mgr.screenshot({ path: "C:/Users/dever/AppData/Local/Temp/shots/lifecycle-reviewed.png", fullPage: true });
await managerCtx.close();
await browser.close();

if (problems.length) {
  console.log(`\n${problems.length} page error(s):`);
  for (const p of [...new Set(problems)].slice(0, 5)) console.log(`  ${p}`);
  failures += 1;
} else {
  console.log("\nNo page errors.");
}
console.log(failures ? `\n${failures} check(s) failed.` : "\nFull lifecycle driven end to end from the UI.");
process.exit(failures ? 1 : 0);
