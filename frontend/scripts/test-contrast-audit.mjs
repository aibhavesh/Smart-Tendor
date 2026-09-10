/**
 * Self-test for the AA contrast auditor.
 *
 * A checker that cannot fail is worse than no checker: it converts "unverified" into a
 * green tick. These are known-answer cases run through the *same* exported function the
 * conformance runner uses, on a blank page — no app or backend required.
 *
 *   node scripts/test-contrast-audit.mjs
 */
import { chromium } from "@playwright/test";
import { auditContrast } from "./lib/contrast-audit.mjs";

// [label, css, text, shouldBeFlagged]
const CASES = [
  ["near-white grey on white, 14px", "color:#bbbbbb;background:#ffffff;font-size:14px", "faint", true],
  ["black on white, 14px", "color:#000000;background:#ffffff;font-size:14px", "solid", false],
  ["25% black on 60% white glass", "color:rgba(0,0,0,0.25);background:rgba(255,255,255,0.6);font-size:13px", "glassy", true],
  ["ink on canvas, 14px", "color:#171717;background:#e5e4e2;font-size:14px", "body", false],
  ["brand blue as 14px text on canvas", "color:#0084ff;background:#e5e4e2;font-size:14px", "link", true],
  ["brand-ink as 14px text on canvas", "color:#005ab5;background:#e5e4e2;font-size:14px", "link", false],
  ["white on brand, 14px bold", "color:#ffffff;background:#0084ff;font-size:14px;font-weight:700", "cta", true],
  ["white on brand-hover, 14px bold", "color:#ffffff;background:#0074e0;font-size:14px;font-weight:700", "cta", false],
  ["grey at 26px counts as large text", "color:#8a8a8a;background:#ffffff;font-size:26px", "big", false],
  ["hidden element must be skipped", "color:#cccccc;background:#ffffff;font-size:12px;display:none", "hidden", false],
];

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto("about:blank");

let failures = 0;
for (const [label, css, text, shouldFlag] of CASES) {
  await page.evaluate(
    ([c, t]) => {
      document.body.innerHTML = "";
      document.body.setAttribute("style", "background:#ffffff");
      const el = document.createElement("div");
      el.setAttribute("style", c);
      el.textContent = t;
      document.body.appendChild(el);
    },
    [css, text],
  );

  const found = await page.evaluate(auditContrast);
  const flagged = found.some((f) => f.text === text);
  const ok = flagged === shouldFlag;
  if (!ok) failures += 1;

  const detail = found.find((f) => f.text === text);
  console.log(
    `${ok ? "PASS" : "FAIL"}  ${label.padEnd(38)} ` +
      `expected ${shouldFlag ? "FLAG" : "clean"}, got ${flagged ? "FLAG" : "clean"}` +
      (detail ? `  (${detail.ratio}:1, need ${detail.threshold})` : ""),
  );
}

await browser.close();
console.log(failures ? `\n${failures} auditor case(s) wrong — do not trust its results.` : "\nAuditor behaves correctly on all known-answer cases.");
process.exit(failures ? 1 : 0);
