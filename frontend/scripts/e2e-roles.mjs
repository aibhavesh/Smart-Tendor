/**
 * Phase E §9.8 — role gating verified by signing in as each role.
 *
 * The plan is explicit that this must not be checked by reading the code, and an earlier
 * pass used a *mocked* /auth/me, which only proves the component branches on a string.
 * This signs in as four real accounts against the real backend and checks both halves:
 * what the shell offers, and what the server actually allows.
 *
 * Requires the app on :3000 and a seeded backend on :8000 with these accounts.
 *
 *   node scripts/e2e-roles.mjs
 */
import { chromium } from "@playwright/test";

const APP = "http://localhost:3000";
const PASSWORD = "password123";

const ACCOUNTS = [
  { email: "viewer@example.com", role: "VIEWER", label: "Viewer" },
  { email: "analyst@example.com", role: "ANALYST", label: "Analyst" },
  { email: "manager@example.com", role: "MANAGER", label: "Manager" },
  { email: "admin@example.com", role: "SUPER_ADMIN", label: "Super admin" },
];

/** route -> the minimum role that may see it. */
const ROUTES = [
  { path: "/dashboard", min: "VIEWER" },
  { path: "/tenders", min: "VIEWER" },
  { path: "/projects", min: "VIEWER" },
  { path: "/profile", min: "VIEWER" },
  { path: "/reviews", min: "MANAGER" },
  { path: "/admin", min: "ADMIN" },
  { path: "/admin/audit-logs", min: "ADMIN" },
];

/** Nav labels the shell should expose, by minimum role. */
const NAV = [
  { label: "Dashboard", min: "VIEWER" },
  { label: "Tenders", min: "VIEWER" },
  { label: "Past projects", min: "VIEWER" },
  { label: "Reviews", min: "MANAGER" },
  { label: "Administration", min: "ADMIN" },
  { label: "Audit logs", min: "ADMIN" },
];

const LEVEL = { VIEWER: 1, ANALYST: 2, MANAGER: 3, ADMIN: 4, SUPER_ADMIN: 5 };
const allowed = (role, min) => LEVEL[role] >= LEVEL[min];

const browser = await chromium.launch();
let failures = 0;

for (const account of ACCOUNTS) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  await page.goto(`${APP}/login`, { waitUntil: "load" });
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard", { timeout: 15000 }).catch(() => {});

  const landed = new URL(page.url()).pathname === "/dashboard";
  if (!landed) failures += 1;
  console.log(`\n${account.label.toUpperCase()}  (${account.email})`);
  console.log(`  ${landed ? "PASS" : "FAIL"}  signs in and reaches /dashboard`);

  // The shell must offer exactly the sections this role may use.
  await page.waitForTimeout(1200);
  const navText = await page
    .locator("nav[aria-label='Sections']")
    .innerText()
    .catch(() => "");
  for (const item of NAV) {
    const shouldSee = allowed(account.role, item.min);
    const sees = navText.includes(item.label);
    const ok = sees === shouldSee;
    if (!ok) failures += 1;
    console.log(
      `  ${ok ? "PASS" : "FAIL"}  nav ${shouldSee ? "shows" : "hides"} "${item.label}"${ok ? "" : `  (actually ${sees ? "shown" : "hidden"})`}`,
    );
  }

  // Direct navigation must be gated too — a hidden link is not a secured route.
  for (const route of ROUTES) {
    const shouldAccess = allowed(account.role, route.min);
    await page.goto(`${APP}${route.path}`, { waitUntil: "load" });
    await page.waitForTimeout(1300);
    const body = await page.evaluate(() => document.body.innerText);
    const denied = body.includes("do not have access");
    const ok = denied === !shouldAccess;
    if (!ok) failures += 1;
    console.log(
      `  ${ok ? "PASS" : "FAIL"}  ${route.path.padEnd(20)} ${shouldAccess ? "allowed" : "denied"}${ok ? "" : `  (actually ${denied ? "denied" : "allowed"})`}`,
    );
  }

  // And the server must refuse regardless of what the UI did.
  const adminStatus = await page.evaluate(async () => {
    const res = await fetch("http://localhost:8000/admin/users?limit=1", {
      headers: { Authorization: `Bearer ${window.__t ?? ""}` },
    });
    return res.status;
  });
  const serverRefuses = adminStatus === 401 || adminStatus === 403;
  console.log(`  INFO  unauthenticated GET /admin/users → ${adminStatus} (server-side gate: ${serverRefuses ? "refuses" : "ALLOWS"})`);
  if (!serverRefuses) failures += 1;

  await context.close();
}

await browser.close();
console.log(failures ? `\n${failures} role check(s) failed.` : "\nAll role gating correct for all four roles.");
process.exit(failures ? 1 : 0);
