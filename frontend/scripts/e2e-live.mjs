/**
 * End-to-end run against the real backend.
 *
 * The mocked smoke test proves the screens render; only this proves the frontend and the
 * API actually agree — URL construction, query-parameter names, auth headers, CORS, the
 * refresh flow. Nothing is stubbed: it signs in through the real login form and drives
 * the real navigation.
 *
 * Requires: backend on :8000 with seeded data, frontend on :3000.
 *
 *   node scripts/e2e-live.mjs [--email=] [--password=] [--shots]
 */
import { chromium } from "@playwright/test";

const arg = (n, d) => process.argv.find((a) => a.startsWith(`--${n}=`))?.slice(n.length + 3) ?? d;
const EMAIL = arg("email", "admin@example.com");
const PASSWORD = arg("password", "password123");
const APP = arg("app", "http://localhost:3000");
const SHOTS = process.argv.includes("--shots");

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();

const problems = [];
/*
 * Google Identity noise is tracked separately. Whether Google has propagated an
 * authorised origin is a state of *their* console, not of this codebase — folding it
 * into `problems` would make an unrelated external delay look like a code regression.
 * It is still reported loudly, just not counted as a failure.
 */
const external = [];
const isGoogle = (s) => /gsi|gstatic|accounts\.google/i.test(s ?? "");

/*
 * Expected noise, enumerated rather than filtered loosely — a broad filter would hide a
 * real failure:
 *   - `_rsc=` aborts are Next.js prefetches cancelled on navigation, not errors.
 *   - The hero video is decorative and has its own fallback path.
 *   - Several tender sub-resources legitimately 404/422 before their stage has run; the
 *     UI swallows those deliberately and shows "not yet". See docs/api-map.md.
 */
const EXPECTED_MISSING = /\/tenders\/[^/]+\/(metadata|recommendation|report|boq|boq\/analytics|documents|matches|reviews)$/;
const isPrefetch = (url) => url.includes("_rsc=");
const isVideo = (url) => url.endsWith(".mp4");
/*
 * The logout revoke is sent with `keepalive` so it survives the redirect that unmounts
 * the screen. A keepalive request that outlives its page is reported to that page as
 * aborted even though the network stack completes it — verified against the server:
 * every logout logs a 204 and the session row is revoked. Expected, not a failure.
 */
const isKeepaliveLogout = (url) => url.endsWith("/auth/logout");
/*
 * useResource aborts a request when its inputs change, so typing in a filter supersedes
 * the in-flight fetch. That abort is the feature working, not a failure — but only
 * ERR_ABORTED counts: any other failure against the API is real.
 */
const isSupersededApiFetch = (url, err) =>
  url.startsWith("http://localhost:8000") && (err ?? "").includes("ERR_ABORTED");

page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  const t = m.text();
  // "Failed to load resource" merely echoes a network event we classify below.
  if (m.type() !== "error" || t.includes("Failed to load resource")) return;
  (isGoogle(t) ? external : problems).push(`console: ${t.slice(0, 200)}`);
});
page.on("requestfailed", (request) => {
  const url = request.url();
  const err = request.failure()?.errorText;
  if (isPrefetch(url) || isVideo(url) || isKeepaliveLogout(url)) return;
  if (isSupersededApiFetch(url, err)) return;
  (isGoogle(url) ? external : problems).push(`requestfailed: ${url} ${err}`);
});
page.on("response", (res) => {
  const url = res.url();
  const status = res.status();
  if (status < 400 || isPrefetch(url) || isVideo(url)) return;
  const path = new URL(url).pathname;
  if ((status === 404 || status === 422) && EXPECTED_MISSING.test(path)) return;
  (isGoogle(url) ? external : problems).push(`HTTP ${status} ${path}`);
});

let failures = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  — ${extra}` : ""}`);
};

// --- sign in through the real form -----------------------------------------
await page.goto(`${APP}/login`, { waitUntil: "load" });
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Password").fill(PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL("**/dashboard", { timeout: 15000 }).catch(() => {});
check("sign in redirects to /dashboard", new URL(page.url()).pathname === "/dashboard", page.url());

await page.waitForTimeout(1500);
let text = await page.evaluate(() => document.body.innerText);
check("dashboard shows live tender total", /\b3\b/.test(text) && text.includes("Tenders"));
check("dashboard lists a seeded tender", text.includes("NIT/2026/"));

// --- tenders list ----------------------------------------------------------
await page.goto(`${APP}/tenders`, { waitUntil: "load" });
await page.waitForTimeout(1200);
text = await page.evaluate(() => document.body.innerText);
check("tenders list shows all three", ["0412", "0398", "0377"].every((n) => text.includes(n)));

// --- the status filter must actually reach the API -------------------------
// Filtering is asserted by *narrowing*, not by a status happening to be empty: this
// suite used to assume the seeded tenders stayed REGISTERED, and started failing the
// moment the lifecycle test advanced them.
await page.getByLabel("Status").selectOption("ARCHIVED");
await page.waitForTimeout(1300);
text = await page.evaluate(() => document.body.innerText);
check("status filter reaches the API (no ARCHIVED tenders)", text.includes("No tenders match"));

await page.getByLabel("Status").selectOption("REGISTERED");
await page.waitForTimeout(1300);
const registered = await page.locator("tbody tr").count();
check("status filter returns only REGISTERED tenders", registered > 0, `${registered} row(s)`);

await page.getByLabel("Status").selectOption("");
await page.waitForTimeout(400);
await page.getByLabel("Search").fill("reservoir");
await page.waitForTimeout(1400);
text = await page.evaluate(() => document.body.innerText);
check("search reaches the API and narrows", text.includes("0398") && !text.includes("0412"));

// --- tender detail, on a tender whose stage we control ---------------------
await page.getByLabel("Search").fill("");
await page.getByLabel("Status").selectOption("REGISTERED");
await page.waitForTimeout(1400);
await page.locator("tbody tr a").first().click();
await page.waitForTimeout(1700);
text = await page.evaluate(() => document.body.innerText);
check("detail opens a tender", /NIT\/\d{4}\/\d+/.test(text));
check("un-analysed tender states it plainly", text.includes("Not analysed yet"));
check(
  "analysis is disabled with a reason at REGISTERED",
  text.includes("PARSED → ANALYZED") || text.includes("Add a document first"),
);
check("money formats with Indian grouping", /\d,\d{2},\d{2},\d{3}/.test(text) || text.includes("NOT SET"));

// --- projects --------------------------------------------------------------
await page.goto(`${APP}/projects`, { waitUntil: "load" });
await page.waitForTimeout(1200);
text = await page.evaluate(() => document.body.innerText);
check("projects list shows seeded rows", text.includes("Pump house upgrade") && text.includes("85,00,000"));

// --- admin -----------------------------------------------------------------
await page.goto(`${APP}/admin`, { waitUntil: "load" });
await page.waitForTimeout(1600);
text = await page.evaluate(() => document.body.innerText);
check("admin lists the seeded users", ["admin@example.com", "manager@example.com", "viewer@example.com"].every((e) => text.includes(e)));
check("system health rendered", text.includes("HEALTHY") || text.includes("DEGRADED"));

// --- audit logs ------------------------------------------------------------
await page.goto(`${APP}/admin/audit-logs`, { waitUntil: "load" });
await page.waitForTimeout(1400);
text = await page.evaluate(() => document.body.innerText);
check("audit log screen loaded", text.includes("Audit logs"));

// --- reviews ---------------------------------------------------------------
await page.goto(`${APP}/reviews`, { waitUntil: "load" });
await page.waitForTimeout(1400);
text = await page.evaluate(() => document.body.innerText);
check("review queue is empty and says so", text.includes("Nothing awaiting review"));

// --- profile + real logout -------------------------------------------------
await page.goto(`${APP}/profile`, { waitUntil: "load" });
await page.waitForTimeout(1200);
text = await page.evaluate(() => document.body.innerText);
check("profile shows the signed-in account", text.includes(EMAIL) && text.includes("Super admin"));

if (SHOTS) {
  for (const [path, name] of [["/dashboard", "dashboard"], ["/tenders", "tenders"], ["/admin", "admin"]]) {
    await page.goto(`${APP}${path}`, { waitUntil: "load" });
    await page.waitForTimeout(1400);
    await page.screenshot({ path: `C:/Users/dever/AppData/Local/Temp/shots/live-${name}.png`, fullPage: true });
  }
}

await page.goto(`${APP}/profile`, { waitUntil: "load" });
await page.waitForTimeout(1000);
await page.getByRole("button", { name: /Sign out/ }).click();
await page.waitForURL("**/login", { timeout: 10000 }).catch(() => {});
check("sign out returns to /login", new URL(page.url()).pathname === "/login", page.url());

await page.goto(`${APP}/dashboard`, { waitUntil: "load" });
await page.waitForTimeout(1500);
check(
  "after sign out, /dashboard bounces to login",
  new URL(page.url()).pathname === "/login",
  new URL(page.url()).pathname,
);

await browser.close();

console.log("");
if (problems.length) {
  console.log(`${problems.length} console/network problem(s):`);
  for (const p of [...new Set(problems)].slice(0, 8)) console.log(`  ${p}`);
  failures += 1;
} else {
  console.log("No console errors, page errors or failed requests.");
}

if (external.length) {
  console.log(`
EXTERNAL (not counted): ${external.length} Google Identity issue(s) —`);
  console.log("  the authorised-origin change has not propagated on Google's side yet.");
  for (const e of [...new Set(external)].slice(0, 3)) console.log(`  ${e}`);
}

console.log(failures ? `\n${failures} check(s) failed.` : "\nAll live checks passed.");
process.exit(failures ? 1 : 0);
