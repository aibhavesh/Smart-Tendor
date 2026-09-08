/**
 * Phase E §9.7 — every screen has loading, empty and error states, and they are themed.
 *
 * This was the last checklist item left partial: the states are *built*, but "built" is
 * not "reached". Each screen is driven into all three by controlling its API responses —
 * a held response for loading, an empty page for empty, a 500 for error — and the state
 * must actually appear.
 *
 *   node scripts/conformance-states.mjs
 */
import { chromium } from "@playwright/test";

const APP = "http://localhost:3000";
const API = "**localhost:8000/**";
const ADMIN = { email: "admin@example.com", password: "password123" };

/** Screens that fetch, and the marker each state should render. */
const SCREENS = [
  { path: "/dashboard", empty: "No tenders yet" },
  { path: "/tenders", empty: "No tenders" },
  { path: "/reviews", empty: "Nothing awaiting review" },
  { path: "/projects", empty: "No past projects yet" },
  { path: "/admin", empty: null }, // users list is never empty — the caller is a user
  { path: "/admin/audit-logs", empty: "No entries match" },
];

const EMPTY_PAGE = { items: [], total: 0, limit: 20, offset: 0, has_more: false };

let failures = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  — ${extra}` : ""}`);
};

const browser = await chromium.launch();

/** Auth calls must always succeed, whatever we do to the data endpoints. */
const isAuth = (path) => path.startsWith("/auth/");

/*
 * Each scenario signs in for itself.
 *
 * Reusing one captured `storageState` does not work here: the access token lives in
 * memory, so a fresh context must exchange the *refresh* token — and refresh tokens
 * rotate, so replaying the same one across contexts fails after the first. Every screen
 * would then quietly bounce to /login and report a missing state that is in fact fine.
 */
async function scenario(fn) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();

  await page.goto(`${APP}/login`, { waitUntil: "load" });
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard", { timeout: 20000 }).catch(() => {});

  const signedIn = new URL(page.url()).pathname === "/dashboard";
  if (!signedIn) {
    check("sign-in for scenario", false, `landed on ${new URL(page.url()).pathname}`);
    await ctx.close();
    return;
  }

  await fn(page, ctx);
  await ctx.close();
}

for (const screen of SCREENS) {
  // --- loading -------------------------------------------------------------
  await scenario(async (page) => {
    await page.route(API, async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (isAuth(path)) return route.continue();
      await new Promise((r) => setTimeout(r, 6000)); // hold it open
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(EMPTY_PAGE) });
    });
    await page.goto(`${APP}${screen.path}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    const busy = await page.locator('[aria-busy="true"], .animate-pulse').count();
    check(`§9.7 loading   ${screen.path}`, busy > 0, busy === 0 ? "no skeleton rendered" : "");
  });

  // --- empty ---------------------------------------------------------------
  if (screen.empty) {
    await scenario(async (page) => {
      await page.route(API, (route) => {
        const path = new URL(route.request().url()).pathname;
        if (isAuth(path)) return route.continue();
        const body = path === "/stats"
          ? { tenders_total: 0, tenders_by_status: {}, past_projects_total: 0, reviews_pending: 0 }
          : EMPTY_PAGE;
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
      });
      await page.goto(`${APP}${screen.path}`, { waitUntil: "load" });
      await page.waitForTimeout(1800);
      const text = await page.evaluate(() => document.body.innerText);
      check(`§9.7 empty     ${screen.path}`, text.includes(screen.empty), screen.empty);
    });
  }

  // --- error ---------------------------------------------------------------
  await scenario(async (page) => {
    await page.route(API, (route) => {
      const path = new URL(route.request().url()).pathname;
      if (isAuth(path)) return route.continue();
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "boom" }) });
    });
    await page.goto(`${APP}${screen.path}`, { waitUntil: "load" });
    await page.waitForTimeout(2000);
    const text = await page.evaluate(() => document.body.innerText);
    const shown = text.includes("Something went wrong") || text.includes("Try again");
    check(`§9.7 error     ${screen.path}`, shown, shown ? "" : "no error state rendered");
  });
}

await browser.close();
console.log(
  failures
    ? `\n${failures} state(s) missing — §9.7 not satisfied.`
    : "\nEvery screen renders loading, empty and error states.",
);
process.exit(failures ? 1 : 0);
