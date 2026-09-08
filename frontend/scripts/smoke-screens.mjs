/**
 * Screen smoke test against a mocked API.
 *
 * TypeScript proves the shapes line up; it does not prove a screen survives real JSON —
 * a null `closing_date`, an empty `applied_rules`, an UNKNOWN metadata field. This mounts
 * every authenticated screen with fixtures matching the verified schemas, and fails on any
 * uncaught error or React console error.
 *
 * Fixtures are deliberately awkward: nulls, empty arrays, is_known:false, a FAILED
 * document. The happy path is the one least likely to break.
 *
 *   node scripts/smoke-screens.mjs [--role=ADMIN] [--shots]
 */
import { chromium } from "@playwright/test";

const arg = (n, d) => process.argv.find((a) => a.startsWith(`--${n}=`))?.slice(n.length + 3) ?? d;
const ROLE = arg("role", "SUPER_ADMIN");
const SHOTS = process.argv.includes("--shots");

const TENDER_ID = "11111111-1111-4111-8111-111111111111";

const tender = (over = {}) => ({
  id: TENDER_ID,
  tender_number: "NIT/2026/0412",
  title: "Supply and installation of pumping machinery",
  status: "ANALYZED",
  description: null,
  estimated_value: "42000000.00",
  closing_date: null, // deliberately null
  source_url: null,
  department: null,
  created_at: "2026-08-01T10:00:00Z",
  updated_at: "2026-08-10T10:00:00Z",
  ...over,
});

const paged = (items, total = items.length) => ({
  items,
  total,
  limit: 20,
  offset: 0,
  has_more: false,
});

const FIXTURES = {
  "/auth/refresh": {
    access_token: "test-access",
    refresh_token: "test-refresh",
    token_type: "bearer",
    expires_in: 900,
  },
  "/auth/me": {
    id: "u1",
    email: "tester@example.com",
    full_name: "Test User",
    role: ROLE,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    last_login_at: null, // deliberately null
  },
  "/stats": {
    tenders_total: 34,
    tenders_by_status: { REGISTERED: 12, PARSED: 9, ANALYZED: 8, REVIEWED: 5 },
    past_projects_total: 17,
    reviews_pending: 8,
  },
  "/admin/stats": {
    tenders_total: 34,
    tenders_by_status: { REGISTERED: 12, PARSED: 9, ANALYZED: 8, REVIEWED: 5 },
    users_total: 6,
    users_active: 5,
    users_by_role: { VIEWER: 2, ANALYST: 2, MANAGER: 1, ADMIN: 1 },
    past_projects_total: 17,
    reviews_total: 4,
    documents_total: 22,
  },
  "/admin/system-health": {
    healthy: false,
    components: [
      { name: "database", status: "ok", detail: null },
      { name: "vector_store", status: "error", detail: "connection refused" },
    ],
    host: {
      cpu_percent: 12.5,
      memory_percent: 61.2,
      memory_total_mb: 16384,
      memory_used_mb: 10029,
      disk_percent: 44.1,
      disk_total_gb: 512,
      disk_used_gb: 226,
    },
  },
  "/admin/api-usage": {
    total_requests: 1284,
    by_status_class: { "2xx": 1200, "4xx": 78, "5xx": 6 },
    by_method: { GET: 1010, POST: 240, PATCH: 34 },
  },
};

function resolve(pathname) {
  if (FIXTURES[pathname]) return FIXTURES[pathname];

  if (pathname === "/tenders") return paged([tender(), tender({ id: "t2", status: "PARSED" })], 34);
  if (pathname === `/tenders/${TENDER_ID}`) return tender();
  if (pathname.endsWith("/documents"))
    return [
      {
        id: "d1",
        tender_id: TENDER_ID,
        source_url: null,
        file_name: "nit-0412.pdf",
        file_path: null,
        file_size: 91234,
        mime_type: "application/pdf",
        sha256: null,
        status: "FAILED",
        attempt_count: 3,
        last_error: "404 from source",
        downloaded_at: null,
        created_at: "2026-08-02T09:00:00Z",
      },
    ];
  if (pathname.endsWith("/metadata"))
    return {
      tender_id: TENDER_ID,
      known_field_count: 1,
      fields: {
        emd_amount: { value: null, confidence: 0.18, source: null, is_known: false },
        completion_period: { value: "12 months", confidence: 0.91, source: "page 3", is_known: true },
      },
    };
  if (pathname.endsWith("/boq/analytics"))
    return { total_items: 2, items_with_amount: 1, total_value: "1200000.00", categories: [] };
  if (pathname.endsWith("/boq"))
    return [
      {
        id: "b1",
        item_number: null,
        description: "Centrifugal pump, 50 HP",
        unit: null,
        quantity: null,
        unit_rate: null,
        amount: null,
        category: null,
        confidence: 0.44,
      },
    ];
  if (pathname.endsWith("/recommendation"))
    return {
      tender_id: TENDER_ID,
      qualification: {
        qualified: false,
        rules: [
          {
            name: "similar_work_value",
            passed: false,
            detail: "No past project meets the minimum work value.",
            required: "20000000.00",
            actual: "8500000.00",
            qualifying_project_id: null,
            qualifying_project_name: null,
          },
        ],
      },
      risk: {
        overall_severity: "HIGH",
        overall_score: 7.4,
        overall_category: "LIQUIDATED_DAMAGES",
        categories: [
          {
            category: "LIQUIDATED_DAMAGES",
            severity: "HIGH",
            score: 8.1,
            evidence: ["LD at 0.5% per week, capped at 10%"],
            mitigations: [],
          },
        ],
      },
      recommendation: {
        verdict: "NO_BID",
        win_probability: 0,
        confidence: 0.72,
        pros: [],
        cons: ["Qualification not met"],
        document_checklist: [],
        applied_rules: [], // deliberately empty
      },
    };
  if (pathname.endsWith("/report"))
    return {
      tender_id: TENDER_ID,
      verdict: "NO_BID",
      win_probability: 0,
      confidence: 0.72,
      generated_by: "gemini-2.0-flash",
      sections: { executive_summary: "Qualification is the binding constraint here." },
    };
  if (pathname.endsWith("/reviews")) return [];
  if (pathname === "/reviews/pending") return paged([tender()], 8);
  if (pathname === "/projects")
    return paged([
      {
        id: "p1",
        name: "Pump house upgrade",
        client: null,
        work_value: "8500000.00",
        category: null,
        location: null,
        description: null,
        completion_date: null,
        embedding_indexed: false,
        created_at: "2025-03-01T00:00:00Z",
      },
    ]);
  if (pathname === "/admin/users")
    return paged([FIXTURES["/auth/me"], { ...FIXTURES["/auth/me"], id: "u2", email: "b@x.com", role: "VIEWER", is_active: false }]);
  if (pathname === "/admin/audit-logs")
    return paged([
      {
        id: "a1",
        action: "user.role_change",
        entity_type: "User",
        entity_id: "u2",
        actor_id: "u1",
        diff: { role: { before: "VIEWER", after: "ANALYST" } },
        ip_address: null,
        user_agent: null,
        created_at: "2026-08-17T12:00:00Z",
      },
    ]);
  return null;
}

const SCREENS = [
  ["/dashboard", "Dashboard"],
  ["/tenders", "Tenders"],
  [`/tenders/${TENDER_ID}`, "Supply and installation"],
  ["/reviews", "Reviews"],
  ["/projects", "Past projects"],
  ["/admin", "Administration"],
  ["/admin/audit-logs", "Audit logs"],
  ["/profile", "Profile"],
];

const browser = await chromium.launch();
let failures = 0;

for (const [path, expect] of SCREENS) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(() => window.localStorage.setItem("ti.refresh", "test-refresh"));

  const page = await context.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 160)}`);
  });

  await context.route("**localhost:8000/**", async (route) => {
    const url = new URL(route.request().url());
    const body = resolve(url.pathname);
    if (body === null) return route.fulfill({ status: 404, body: '{"detail":"not found"}' });
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto(`http://localhost:3000${path}`, { waitUntil: "load" });
  await page.waitForTimeout(1800);

  const text = await page.evaluate(() => document.body.innerText);
  const rendered = text.includes(expect);
  const clean = problems.length === 0;

  if (!rendered || !clean) failures += 1;
  console.log(
    `${rendered && clean ? "PASS" : "FAIL"}  ${path.padEnd(46)} ${rendered ? "rendered" : "DID NOT RENDER"}`,
  );
  for (const p of problems.slice(0, 3)) console.log(`        ${p}`);

  if (SHOTS) {
    await page.screenshot({
      path: `C:/Users/dever/AppData/Local/Temp/shots/screen-${path.replace(/\W+/g, "-")}.png`,
      fullPage: true,
    });
  }
  await context.close();
}

await browser.close();
console.log(failures ? `\n${failures} screen(s) failed.` : `\nAll ${SCREENS.length} screens render cleanly.`);
process.exit(failures ? 1 : 0);
