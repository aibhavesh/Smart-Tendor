/**
 * Phase E static conformance audit — plan §9 checklist items 1, 2, 3, 5, 6.
 *
 * These are structural properties of the source, so they are checked by reading it rather
 * than by clicking through screens. The runtime half (AA contrast, role gating, state
 * coverage) is covered by conformance-runtime.mjs and e2e-roles.mjs.
 *
 *   node scripts/conformance-static.mjs
 */
import fs from "node:fs";
import path from "node:path";

const SRC = "src";
const TOKEN_FILE = path.join("src", "app", "globals.css");

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.(tsx?|css)$/.test(entry.name)) out.push(full);
  }
  return out;
}

const files = walk(SRC);
const findings = [];
const record = (item, file, line, detail) => findings.push({ item, file, line, detail });

/** Screens are everything under app/ that is not the design gallery. */
const isScreen = (f) => f.includes(path.join("src", "app")) && !f.includes(path.join("app", "design"));

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split(/\r?\n/);
  const isTokenFile = path.normalize(file) === path.normalize(TOKEN_FILE);

  lines.forEach((line, i) => {
    const n = i + 1;
    const code = line.replace(/\/\/.*$/, ""); // ignore trailing line comments

    // 1 — literal colour values outside the token file
    if (!isTokenFile) {
      if (/#[0-9a-fA-F]{3,8}\b/.test(code) && !/#[0-9a-fA-F]*[g-zG-Z]/.test(code)) {
        // Exclude in-page anchors like #home and svg url(#id)
        const hits = code.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
        for (const h of hits) {
          if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(h)) {
            record(1, file, n, `literal colour ${h}`);
          }
        }
      }
      if (/\b(rgba?|hsla?)\(/.test(code)) record(1, file, n, "rgb()/hsl() literal");
    }

    // 2 — local font declarations outside the root layout
    const isRootLayout = file.endsWith(path.join("app", "layout.tsx"));
    if (!isRootLayout && !isTokenFile) {
      if (/next\/font/.test(code)) record(2, file, n, "next/font imported outside root layout");
      if (/@font-face/.test(code)) record(2, file, n, "@font-face outside the token file");
      if (/font-family\s*:/.test(code)) record(2, file, n, "raw font-family declaration");
    }

    // 3 — backgrounds and surfaces must come from tokens
    if (isScreen(file)) {
      // bg-white is legitimate for glass surfaces (white/NN); a *solid* bg-white is not.
      const solidWhite = /\bbg-white(?!\/)/.test(code);
      if (solidWhite) record(3, file, n, "solid bg-white (use a surface token or white/NN)");
      if (/\bbg-(slate|gray|zinc|stone|neutral)-\d{2,3}\b/.test(code)) {
        record(3, file, n, "Tailwind palette background instead of a token");
      }
    }

    // 5 — verdict/risk states must use the shared badges
    if (isScreen(file) && !/Badge/.test(text)) {
      if (/["'`](GO|NO_BID|REVIEW)["'`]/.test(code)) {
        record(5, file, n, "verdict literal in a file that imports no badge");
      }
      if (/["'`](NONE|LOW|MEDIUM|HIGH)["'`]/.test(code)) {
        record(5, file, n, "risk literal in a file that imports no badge");
      }
    }

    // 6 — charts must use the shared theme
    if (/from\s+"recharts"/.test(code) && !/CHART_THEME/.test(text)) {
      record(6, file, n, "recharts imported without CHART_THEME");
    }
  });
}

const LABEL = {
  1: "No literal colour values",
  2: "Fonts inherited from the root layout",
  3: "Backgrounds/surfaces from tokens only",
  5: "Verdict/risk use the shared badges",
  6: "Charts use the shared chart theme",
};

console.log(`Scanned ${files.length} files under ${SRC}/\n`);
let failed = 0;
for (const item of [1, 2, 3, 5, 6]) {
  const hits = findings.filter((f) => f.item === item);
  if (hits.length === 0) {
    console.log(`PASS  §9.${item}  ${LABEL[item]}`);
  } else {
    failed += 1;
    console.log(`FAIL  §9.${item}  ${LABEL[item]}  — ${hits.length} finding(s)`);
    for (const h of hits.slice(0, 8)) {
      console.log(`        ${h.file}:${h.line}  ${h.detail}`);
    }
    if (hits.length > 8) console.log(`        …and ${hits.length - 8} more`);
  }
}

console.log(failed ? `\n${failed} checklist item(s) failing.` : "\nAll static checklist items pass.");
process.exit(failed ? 1 : 0);
