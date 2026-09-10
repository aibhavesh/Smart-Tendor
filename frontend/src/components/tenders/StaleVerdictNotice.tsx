import { AlertTriangle } from "lucide-react";

/*
 * Shown wherever a recommendation, its confidence score, or the analyst
 * commentary is displayed, when the tender's recorded verdict predates a
 * metadata correction.
 *
 * Two things this deliberately does NOT say:
 *
 *   - It does not claim the recommendation is stale. Recommendations are never
 *     stored; the one on screen was recomputed from corrected data. Saying
 *     otherwise would tell a manager to distrust the most current thing here.
 *   - It does not hide, grey out, or truncate anything. A manager may still
 *     need to read the recommendation in order to judge whether the correction
 *     changes the decision at all.
 *
 * It is a prompt to act. Nothing recomputes on its own.
 */
export function StaleVerdictNotice({ className = "" }: { className?: string }) {
  return (
    <p
      role="status"
      className={`flex items-start gap-2 rounded-control border border-brand/30 bg-brand/10 px-3 py-2 text-caption font-semibold text-ink ${className}`}
    >
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-brand-deep" aria-hidden="true" />
      <span>
        The recorded verdict predates a metadata correction. The figures below have been
        recomputed from the corrected data — re-confirm the decision before relying on it.
      </span>
    </p>
  );
}
