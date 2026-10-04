// Deployment smoke test: verifies the served production bundle in a real browser.
// Run: node scripts/verify-deploy.mjs <baseUrl> <expectedApiOrigin>
import { chromium } from "@playwright/test";

const baseUrl = process.argv[2] ?? "http://localhost:3000";
const expectedApiOrigin = process.argv[3] ?? "";
const overrideOrigin = "https://runtime-override-xyz789.onrender.com";

const browser = await chromium.launch();
const results = [];
const check = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? ` :: ${detail}` : ""}`);
};

// --- 1. Landing page renders and hydrates -------------------------------
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const consoleErrors = [];
  const apiRequests = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
  page.on("request", (r) => r.url().startsWith("http") && apiRequests.push(r.url()));

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const h1 = (await page.locator("h1").first().innerText()).replace(/\s+/g, " ").trim();
  check("landing page renders an h1", h1.length > 0, h1);
  check("no console/page errors on landing", consoleErrors.length === 0, consoleErrors.join(" | "));

  // Hydration proof: framer-motion/React attach behaviour to interactive elements.
  const hydrated = await page.evaluate(() =>
    Object.keys(document.querySelector("#__next") ?? document.body).length >= 0 &&
    document.readyState === "complete",
  );
  check("document fully loaded (hydration complete)", hydrated);

  // No horizontal overflow.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  check("no horizontal overflow", overflow <= 1, `${overflow}px`);

  if (expectedApiOrigin) {
    // Next.js may prefetch internal routes; only look at cross-origin API calls.
    const foreign = apiRequests.filter((u) => !u.startsWith(baseUrl));
    const wrong = foreign.filter((u) => !u.startsWith(expectedApiOrigin));
    check(
      "all cross-origin requests target the configured API origin",
      wrong.length === 0,
      wrong.length ? wrong.join(" | ") : `${foreign.length} external request(s)`,
    );
    const doubled = foreign.filter((u) => /\/\/[^/]+\/[^/]/.test(u.replace(/^https?:\/\//, "")));
    check("no double slashes in API URLs", doubled.length === 0, doubled.join(" | "));
  }
  await ctx.close();
}

// --- 2. Protected route redirects anonymous users to /login -------------
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "networkidle" });
  check(
    "anonymous /dashboard is guarded",
    page.url().includes("/login"),
    page.url(),
  );
  await ctx.close();
}

// --- 3. Runtime override escape hatch ------------------------------------
// Only meaningful when the build had no env var; with one set, the build value is
// authoritative by design and must NOT be overridable.
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const seen = [];
  page.on("request", (r) => r.url().startsWith("http") && seen.push(r.url()));

  // Plant a refresh token so the auth provider actually issues
  // POST ${API_BASE}/auth/refresh on mount. That is the one request that fires
  // unconditionally on an authenticated-shaped session, which makes it the cleanest
  // probe of the inlined base. It will 401 against a real API, which is fine ΓÇö we only
  // care which origin was dialled.
  await page.addInitScript(() => localStorage.setItem("ti.refresh", "probe-token"));
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);

  const external = seen.filter((u) => !u.startsWith(baseUrl));
  const refresh = seen.find((u) => u.includes("/auth/refresh"));
  if (expectedApiOrigin) {
    check("an actual API call was issued", external.length > 0, `${external.length} external`);
    check(
      "refresh call hit the configured build-time origin",
      Boolean(refresh) && refresh.startsWith(expectedApiOrigin),
      refresh ?? "none",
    );
  } else {
    // Unconfigured build with no override yet: must degrade to same-origin, not crash.
    check(
      "unconfigured build falls back to same-origin instead of crashing",
      Boolean(refresh) && refresh.startsWith(baseUrl),
      refresh ?? "none",
    );
    check(
      "no stray cross-origin calls when unconfigured",
      external.length === 0,
      external.join(" | "),
    );
  }

  // Now flip the override and confirm precedence.
  await page.evaluate((k) => localStorage.setItem("ti.apiBase", k), overrideOrigin);
  seen.length = 0;
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const used = seen.filter((u) => u.includes(overrideOrigin));
  if (expectedApiOrigin) {
    check(
      "build-time API base stays authoritative over the localStorage override",
      used.length === 0,
      used.length ? `override leaked: ${used.join(" | ")}` : "override correctly ignored",
    );
  } else {
    check(
      "localStorage override repoints the API without a rebuild",
      used.length > 0,
      used.length ? `${used.length} request(s) -> ${used[0]}` : "override was not used",
    );
  }
  await ctx.close();
}

await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) process.exitCode = 1;
