/**
 * The chart theme (plan §7) — one shared config object, never per-chart props.
 *
 * Values are `var(--color-*)` rather than literals so charts track the theme and the
 * token lint rules stay satisfied. Browsers resolve custom properties in SVG
 * presentation attributes, which is how Recharts applies stroke and fill.
 */

export const CHART_THEME = {
  /** Gridlines and axis rules — deliberately faint. */
  grid: "var(--color-ink-strong)",
  gridOpacity: 0.08,
  axis: "var(--color-ink-muted)",
  axisFontSize: 11,

  /**
   * Categorical series order. Brand blue leads; green and violet follow. Semantic
   * colours (go / danger) are reserved for verdict and risk meaning — do not spend
   * them on an arbitrary third series.
   */
  series: [
    "var(--color-brand)",
    "var(--color-state-go)",
    "var(--color-accent-violet)",
    "var(--color-sky-vivid)",
    "var(--color-brand-deep)",
  ],

  /** Sequential ramp for a single measure. */
  ramp: ["var(--color-sky-soft)", "var(--color-sky-vivid)", "var(--color-brand)", "var(--color-brand-deep)"],

  /** Severity ramp — pairs with RiskBadge, and never used decoratively. */
  severity: {
    NONE: "var(--color-ink-muted)",
    LOW: "var(--color-state-go-ink)",
    MEDIUM: "var(--color-brand-deep)",
    HIGH: "var(--color-state-danger)",
  },

  /** Verdict colours — pairs with VerdictBadge. */
  verdict: {
    GO: "var(--color-state-go-ink)",
    REVIEW: "var(--color-brand-deep)",
    NO_BID: "var(--color-state-danger)",
  },

  tooltip: {
    contentStyle: {
      background: "var(--color-canvas)",
      border: "1px solid var(--color-ink-strong)",
      borderRadius: "var(--radius-tile)",
      fontSize: "var(--text-caption)",
      color: "var(--color-ink)",
    },
    labelStyle: { color: "var(--color-ink-muted)", fontSize: "var(--text-mini)" },
  },
} as const;
