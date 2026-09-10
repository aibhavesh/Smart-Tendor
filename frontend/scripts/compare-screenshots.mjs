/**
 * Pixel diff between two PNGs.
 *
 * Plan §6.5 requires the token refactor to leave the landing page rendering
 * identically to its pre-refactor screenshot. "Looks the same to me" is not that
 * claim, so this counts differing pixels and writes a diff image when they exist.
 *
 *   node scripts/compare-screenshots.mjs <before.png> <after.png> [diff.png]
 *
 * Exit 0 when identical, 1 otherwise.
 */
import fs from "node:fs";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const [, , beforePath, afterPath, diffPath] = process.argv;

if (!beforePath || !afterPath) {
  console.error("usage: node scripts/compare-screenshots.mjs <before.png> <after.png> [diff.png]");
  process.exit(2);
}

const before = PNG.sync.read(fs.readFileSync(beforePath));
const after = PNG.sync.read(fs.readFileSync(afterPath));

if (before.width !== after.width || before.height !== after.height) {
  console.error(
    `DIMENSION MISMATCH  before ${before.width}x${before.height}  after ${after.width}x${after.height}`,
  );
  process.exit(1);
}

const diff = new PNG({ width: before.width, height: before.height });
// threshold 0 — any channel difference at all counts. This is a proof, not a vibe check.
const differing = pixelmatch(before.data, after.data, diff.data, before.width, before.height, {
  threshold: 0,
});

const total = before.width * before.height;
const pct = ((differing / total) * 100).toFixed(4);

if (differing === 0) {
  console.log(`IDENTICAL  0 of ${total.toLocaleString()} pixels differ`);
  process.exit(0);
}

if (diffPath) {
  fs.writeFileSync(diffPath, PNG.sync.write(diff));
  console.log(`diff image: ${diffPath}`);
}
console.log(`DIFFERS  ${differing.toLocaleString()} of ${total.toLocaleString()} pixels (${pct}%)`);
process.exit(1);
