import { UnknownValue } from "./Badge";
import type { ReactNode } from "react";

/*
 * Extraction confidence (PRD FR / plan §7).
 *
 * The backend returns `confidence` 0.0–1.0 on every extracted field, plus `is_known`.
 * Both must be visible wherever an extracted value is shown, so `ExtractedField` below
 * is the only sanctioned way to render one — it makes forgetting the confidence, or
 * rendering UNKNOWN as an empty cell, the harder path.
 */

/** Bucket only affects emphasis, never meaning — the number is always shown. */
function band(confidence: number): { bar: string; text: string; label: string } {
  if (confidence >= 0.8) return { bar: "bg-state-go-ink", text: "text-ink", label: "high" };
  if (confidence >= 0.5) return { bar: "bg-brand-deep", text: "text-ink", label: "medium" };
  return { bar: "bg-state-danger", text: "text-state-danger-ink", label: "low" };
}

export function ConfidenceMeter({ confidence }: { confidence: number }) {
  const clamped = Math.min(1, Math.max(0, confidence));
  const { bar, text, label } = band(clamped);
  const pct = Math.round(clamped * 100);

  return (
    <span
      className="inline-flex items-center gap-1.5 align-middle"
      title={`Extraction confidence: ${clamped.toFixed(2)} (${label})`}
    >
      <span
        className="h-1 w-10 rounded-full bg-ink-strong/10 overflow-hidden shrink-0"
        role="img"
        aria-label={`Extraction confidence ${clamped.toFixed(2)} out of 1, ${label}`}
      >
        <span className={`block h-full rounded-full ${bar}`} style={{ width: `${pct}%` }} />
      </span>
      <span className={`text-mini font-semibold tabular-nums ${text}`}>{clamped.toFixed(2)}</span>
    </span>
  );
}

/**
 * Renders an extracted value together with its confidence, or the UNKNOWN treatment.
 * Mirrors the backend's MetadataFieldResponse shape.
 */
export function ExtractedField({
  value,
  confidence,
  isKnown,
  source,
}: {
  value: ReactNode;
  confidence: number;
  isKnown: boolean;
  source?: string | null;
}) {
  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      {isKnown && value !== null && value !== "" ? (
        <span className="text-ui text-ink">{value}</span>
      ) : (
        <UnknownValue />
      )}
      <ConfidenceMeter confidence={confidence} />
      {source ? <span className="text-mini text-ink-muted">via {source}</span> : null}
    </span>
  );
}
