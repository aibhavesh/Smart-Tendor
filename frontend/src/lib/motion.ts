/**
 * Motion tokens (plan §7).
 *
 * Framer Motion takes numbers and arrays, not CSS custom properties, so these
 * cannot live in globals.css alone. The `--ease-entrance` / `--duration-*` entries
 * in the @theme block mirror these values for anything styled in CSS — keep the
 * two in step.
 *
 * Values are the landing page's realised motion character, so transitions behind
 * the login feel continuous with the front door rather than like a different app.
 */

/** The landing page's entrance curve — a fast-out, long-settle expo ease. */
export const EASE_ENTRANCE = [0.16, 1, 0.3, 1] as const;

/** Loop easing for the ambient "breathing" drifts. */
export const EASE_FLOAT = "easeInOut" as const;

/** Seconds. Framer Motion works in seconds; the CSS mirror is in ms. */
export const DURATION = {
  /** Overlay fades, colour transitions. */
  quick: 0.2,
  /** Drawer slide. */
  drawer: 0.3,
  /** Header entrance. */
  entrance: 0.6,
  /** Hero column reveal. */
  reveal: 0.9,
} as const;

/** Entrance spring for the suspended badges. */
export const SPRING_BADGE = {
  type: "spring",
  damping: 20,
  stiffness: 100,
} as const;

/** Stagger applied to the badges, in seconds. */
export const BADGE_DELAY = [0.6, 0.8, 1.0] as const;
