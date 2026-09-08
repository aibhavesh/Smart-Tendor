/*
 * Display formatting.
 *
 * Money arrives from the API as a *decimal string* ("42000000.00"), never a number, so a
 * tender value cannot lose precision in transit. Formatting therefore works on the string
 * too — `Number(...)` would be exact for realistic values but sets the precedent that
 * parsing is fine, and one day a value will exceed what a float holds exactly.
 */

/** Indian digit grouping: last three, then pairs — 42000000 → 4,20,00,000. */
function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3);
  return `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${last3}`;
}

/**
 * Format a decimal string for display without parsing it.
 * Trailing ".00" is dropped; other decimals are kept as written.
 */
export function formatDecimal(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;

  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value; // Not a plain decimal — show it untouched rather than mangle it.

  const [, sign, whole, fraction] = match;
  const grouped = groupIndian(whole);
  const keepFraction = fraction && /[1-9]/.test(fraction) ? `.${fraction.replace(/0+$/, "")}` : "";
  return `${sign}${grouped}${keepFraction}`;
}

/** Money, with the rupee symbol. Returns null so callers can render UNKNOWN instead. */
export function formatMoney(value: string | null | undefined): string | null {
  const formatted = formatDecimal(value);
  return formatted === null ? null : `₹ ${formatted}`;
}

/** Acronyms the backend's snake_case keys contain, which title-casing would mangle. */
const ACRONYMS = new Set(["emd", "boq", "oem", "ld", "id", "url", "gst", "pan", "api"]);

/** completion_period → "Completion period"; emd_amount → "EMD amount". */
export function humanise(key: string): string {
  const words = key.split(/[_\s]+/).filter(Boolean);
  return words
    .map((word, i) => {
      if (ACRONYMS.has(word.toLowerCase())) return word.toUpperCase();
      return i === 0 ? word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() : word.toLowerCase();
    })
    .join(" ");
}

/** Dates arrive as ISO strings; show them in the reader's locale, not the server's. */
export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString();
}
