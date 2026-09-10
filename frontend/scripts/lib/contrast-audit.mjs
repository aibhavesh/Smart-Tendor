/**
 * The AA contrast audit, as a browser-evaluatable function source.
 *
 * Kept in its own module so the audit and its self-test share one definition. An earlier
 * version was extracted from the runner with string slicing, which silently produced a
 * broken function that reported zero failures on a page full of them — a checker that
 * cannot fail is worse than no checker.
 */

/** Returns text nodes whose contrast is below the WCAG AA threshold for their size. */
export function auditContrast() {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((v) => parseFloat(v));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const lin = (c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };

  /** Composite every translucent background from the element up to the page. */
  const effectiveBg = (el) => {
    let acc = null;
    for (let n = el; n; n = n.parentElement) {
      const bg = parse(getComputedStyle(n).backgroundColor);
      if (!bg || bg.a === 0) continue;
      acc = acc === null ? bg : over(acc, bg);
      if (acc.a === 1 || bg.a === 1) break;
    }
    return acc ?? { r: 255, g: 255, b: 255, a: 1 };
  };

  const results = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  let node;
  while ((node = walker.nextNode())) {
    const text = node.textContent.trim();
    if (!text) continue;
    const el = node.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);

    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) === 0) continue;
    const box = el.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) continue;

    const fgRaw = parse(cs.color);
    if (!fgRaw) continue;
    const bg = effectiveBg(el);
    const fg = fgRaw.a < 1 ? over(fgRaw, bg) : fgRaw;

    const px = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    // WCAG "large text": >=24px, or >=18.66px when bold.
    const large = px >= 24 || (px >= 18.66 && weight >= 700);
    const threshold = large ? 3.0 : 4.5;
    const r = ratio(fg, bg);

    if (r < threshold) {
      results.push({
        text: text.slice(0, 45),
        ratio: Math.round(r * 100) / 100,
        threshold,
        px: Math.round(px * 10) / 10,
        weight,
        color: cs.color,
      });
    }
  }
  return results;
}
