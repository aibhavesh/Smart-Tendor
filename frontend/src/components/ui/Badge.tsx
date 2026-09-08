import { AlertTriangle, Check, CircleHelp, Minus, Search, ShieldAlert, X } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

/*
 * Verdict, risk and UNKNOWN badges.
 *
 * Two rules hold throughout, both from the PRD:
 *   - Never colour alone. Every state pairs its colour with a label AND an icon, so it
 *     survives greyscale printing and colour-blind readers.
 *   - Solid fill + white text. Measured, tinted variants of this palette sat under AA
 *     (see scripts/check-contrast.mjs); the solid fills clear it at 4.83–7.68:1.
 */

export type Verdict = "GO" | "REVIEW" | "NO_BID";
export type RiskLevel = "NONE" | "LOW" | "MEDIUM" | "HIGH";

const SHELL =
  "inline-flex items-center gap-1.5 rounded-full font-black tracking-wide whitespace-nowrap";
const SIZE = "px-2.5 py-1 text-mini";

function Pill({
  className,
  icon: Icon,
  children,
}: {
  className: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  children: ReactNode;
}) {
  return (
    <span className={`${SHELL} ${SIZE} ${className}`}>
      <Icon className="w-3 h-3 shrink-0" aria-hidden={true} />
      {children}
    </span>
  );
}

const VERDICT = {
  GO: { className: "bg-state-go-ink text-white", icon: Check, label: "GO" },
  REVIEW: { className: "bg-brand-deep text-white", icon: Search, label: "REVIEW" },
  NO_BID: { className: "bg-state-danger text-white", icon: X, label: "NO BID" },
} as const;

/** GO / REVIEW / NO_BID. The verdict is rule-derived — never present it as an opinion. */
export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const v = VERDICT[verdict];
  return (
    <Pill className={v.className} icon={v.icon}>
      {v.label}
    </Pill>
  );
}

const RISK = {
  NONE: { className: "bg-ink-muted text-white", icon: Minus, label: "NONE" },
  LOW: { className: "bg-state-go-ink text-white", icon: Check, label: "LOW" },
  MEDIUM: { className: "bg-brand-deep text-white", icon: ShieldAlert, label: "MEDIUM" },
  HIGH: { className: "bg-state-danger text-white", icon: AlertTriangle, label: "HIGH" },
} as const;

/** NONE / LOW / MEDIUM / HIGH. */
export function RiskBadge({ level }: { level: RiskLevel }) {
  const r = RISK[level];
  return (
    <Pill className={r.className} icon={r.icon}>
      {r.label}
    </Pill>
  );
}

/**
 * UNKNOWN is a deliberate, honest output of extraction — not a missing value and not a
 * rendering bug. It gets its own visual state: a dashed outline chip that reads as
 * "we looked and could not tell", never an empty cell.
 */
export function UnknownValue({ label = "UNKNOWN" }: { label?: string }) {
  return (
    <span
      className={`${SHELL} px-2.5 py-1 text-mini border border-dashed border-ink-muted text-ink-muted bg-transparent`}
      title="Not present in the source document"
    >
      <CircleHelp className="w-3 h-3 shrink-0" aria-hidden={true} />
      {label}
    </span>
  );
}
