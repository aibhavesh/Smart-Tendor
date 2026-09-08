/**
 * Phase E runtime conformance — plan §9 checklist items 4 and 7.
 *
 * Item 4 (AA contrast) cannot be settled from source: the palette being accessible does
 * not prove a screen combines it correctly. This walks the rendered DOM of every screen,
 * resolves each text node's effective foreground and background — compositing through
 * translucent ancestors, which is where this theme's glass surfaces would hide a
 * failure — and measures the real ratio.
 *
 * Requires the app on :3000 and a seeded backend on :8000.
 *
 *   node scripts/conformance-runtime.mjs [--email=] [--password=]
 */
import { chromium } from "@playwright/test";
import { auditContrast } from "./lib/contrast-audit.mjs";

const arg = (n, d) => process.argv.find((a) => a.startsWith(`--${n}=`))?.slice(n.length + 3) ?? d;
const EMAIL = arg("email", "admin@example.com");
const PASSWORD = arg("password", "password123");
const APP = "http://localhost:3000";

const SCREENS = [
  "/", "/login", "/register", "/forgot-password",
  "/dashboard", "/tenders", "/reviews", "/projects",
  "/admin", "/admin/audit-logs", "/profile",
];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();

// Sign in once so the authenticated screens render real content.
await page.goto(`${APP}/login`, { waitUntil: "load" });
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Password").fill(PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL("**/dashboard", { timeout: 15000 }).catch(() => {});

let failures = 0;
for (const path of SCREENS) {
  await page.goto(`${APP}${path}`, { waitUntil: "load" });
  await page.waitForTimeout(1600);
  const bad = await page.evaluate(auditContrast);

  if (bad.length === 0) {
    console.log(`PASS  §9.4  ${path}`);
  } else {
    failures += 1;
    console.log(`FAIL  §9.4  ${path}  — ${bad.length} text node(s) below AA`);
    for (const b of bad.slice(0, 5)) {
      console.log(`        ${b.ratio}:1 (need ${b.threshold}) ${b.px}px/${b.weight}  ${JSON.stringify(b.text)}`);
    }
    if (bad.length > 5) console.log(`        …and ${bad.length - 5} more`);
  }
}

await browser.close();
console.log(failures ? `\n${failures} screen(s) with contrast failures.` : "\nEvery text node on every screen meets AA.");
process.exit(failures ? 1 : 0);
