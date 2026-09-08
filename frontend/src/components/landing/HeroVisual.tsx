"use client";

import { useEffect, useRef, useState, type ComponentType } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { EASE_ENTRANCE, EASE_FLOAT, DURATION, SPRING_BADGE } from "@/lib/motion";
import { BadgeCheck, Check, FileSpreadsheet } from "lucide-react";

/*
 * Right column: ambient aura, concentric orbital rings, the robot companion video, and
 * three liquid-glass badges suspended at the prompt's anchors with its breathing loops.
 *
 * The video is the one asset here fetched over the network, so it is the one thing that
 * can fail to load. Two consequences are handled: `onError`
 * swaps in a self-hosted DOM panel rather than leaving a hole; and because the badge
 * anchors were drawn to overlap a video (nothing readable underneath), the fallback
 * panel uses wider xl-only anchors so they overhang its edges instead of its content.
 */

/**
 * Self-hosted since the licence was cleared (2026-08-18). Same-origin means no extra DNS
 * or TLS handshake, no third-party runtime dependency, and the page works offline.
 * `NEXT_PUBLIC_HERO_VIDEO` still overrides it — e.g. to point at a CDN in production.
 */
const HERO_VIDEO = process.env.NEXT_PUBLIC_HERO_VIDEO ?? "/video/hero.mp4";

const GLASS =
  "bg-gradient-to-br from-surface/75 to-surface/45 border border-surface/70 ring-1 ring-ink-strong/5 backdrop-blur-glass";

type FloatSpec = {
  y: [number, number, number];
  x: [number, number, number];
  duration: number;
  rotate: number;
};

type BadgeSpec = {
  /** Prompt anchors — used over the video, where overlap is pure decoration. */
  anchor: string;
  /** Wider, xl-only anchors — used over the fallback panel, which has readable content. */
  safeAnchor: string;
  shadowClass: string;
  bead: string;
  beadShadowClass: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  iconClassName?: string;
  primary: string;
  secondary: string;
  delay: number;
  float: FloatSpec;
};

const BADGES: BadgeSpec[] = [
  {
    // Base offset pulled in from the prompt's -right-4: on a phone the wrapper starts at
    // the page's own 24px gutter, so -right-4 puts the badge corner on the viewport edge.
    anchor: "absolute top-[18%] -right-1 sm:-right-10 md:-right-14",
    safeAnchor: "hidden xl:block absolute top-[18%] -right-20",
    shadowClass: "shadow-badge-brand",
    bead: "from-brand to-brand-deep",
    beadShadowClass: "shadow-bead-brand",
    icon: FileSpreadsheet,
    primary: "Extract the BOQ",
    secondary: "items and rates",
    delay: 0.6,
    float: { y: [0, -8, 0], x: [0, 2, 0], duration: 5.0, rotate: 1 },
  },
  {
    anchor: "absolute top-[48%] -left-2 sm:-left-12 md:-left-16",
    safeAnchor: "hidden xl:block absolute top-[48%] -left-24",
    shadowClass: "shadow-badge-go",
    bead: "from-state-go to-state-go-deep",
    beadShadowClass: "shadow-bead-go",
    icon: BadgeCheck,
    primary: "Qualification",
    secondary: "vs past projects",
    delay: 0.8,
    float: { y: [0, 8, 0], x: [0, -2, 0], duration: 5.5, rotate: -1 },
  },
  {
    anchor: "absolute bottom-[18%] -right-1 sm:-right-8 md:-right-12",
    safeAnchor: "hidden xl:block absolute bottom-[18%] -right-20",
    shadowClass: "shadow-badge-violet",
    bead: "from-accent-violet to-accent-violet-deep",
    beadShadowClass: "shadow-bead-violet",
    icon: Check,
    iconClassName: "stroke-[3px]",
    primary: "GO or NO_BID",
    secondary: "with rule trail",
    delay: 1.0,
    float: { y: [0, -10, 0], x: [0, -1, 0], duration: 4.8, rotate: 1.5 },
  },
];

function FloatingBadge({ spec, safe }: { spec: BadgeSpec; safe: boolean }) {
  const reduceMotion = useReducedMotion();
  const Icon = spec.icon;

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ ...SPRING_BADGE, delay: spec.delay }}
      className={safe ? spec.safeAnchor : spec.anchor}
    >
      <motion.div
        animate={reduceMotion ? undefined : { y: spec.float.y, x: spec.float.x }}
        transition={{ duration: spec.float.duration, ease: EASE_FLOAT, repeat: Infinity }}
      >
        <motion.div
          whileHover={reduceMotion ? undefined : { scale: 1.05, rotate: spec.float.rotate }}
          className={`${GLASS} ${spec.shadowClass} px-5 py-3 rounded-badge flex items-center gap-3 pointer-events-auto`}
        >
          <span
            className={`w-8 h-8 rounded-control bg-gradient-to-br ${spec.bead} ${spec.beadShadowClass} flex items-center justify-center shrink-0`}
          >
            <Icon className={`w-4 h-4 text-white ${spec.iconClassName ?? ""}`} aria-hidden={true} />
          </span>
          <span className="flex flex-col text-left leading-tight">
            <span className="font-black text-label text-ink tracking-tight whitespace-nowrap">
              {spec.primary}
            </span>
            <span className="font-semibold text-micro text-ink-muted mt-0.5 whitespace-nowrap">
              {spec.secondary}
            </span>
          </span>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}

/** DOM stand-in shown only if the video cannot be loaded. */
function PreviewPanel() {
  return (
    <div
      className={`${GLASS} shadow-panel rounded-panel px-8 py-6 select-none`}
    >
      <div className="flex items-center gap-3">
        <div className="flex flex-col">
          <span className="text-micro font-semibold text-ink-muted tracking-wide">TENDER</span>
          <span className="font-outfit font-bold text-ui-lg text-ink tracking-tight">
            NIT/2026/0412
          </span>
        </div>
        <span className="px-3 py-1 rounded-full bg-state-go text-white text-mini font-black tracking-wide">
          GO
        </span>
      </div>

      {/* Stacked below sm: "QUALIFICATION" is one unbreakable word and overflows a
          third-width tile on a phone. */}
      <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: "Qualification", value: "Passed" },
          { label: "Risk", value: "Medium" },
          { label: "Confidence", value: "0.86" },
        ].map((metric) => (
          <div
            key={metric.label}
            className="rounded-tile bg-surface/60 border border-surface/70 px-3 py-2.5"
          >
            <span className="block text-nano font-semibold text-ink-muted tracking-wide">
              {metric.label.toUpperCase()}
            </span>
            <span className="block font-outfit font-bold text-ui text-ink mt-0.5">
              {metric.value}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-col gap-2.5">
        {[
          { label: "Civil works", share: 82 },
          { label: "Electrical", share: 54 },
          { label: "Instrumentation", share: 31 },
        ].map((row) => (
          <div key={row.label} className="flex items-center gap-3">
            <span className="w-[104px] shrink-0 text-mini font-medium text-ink-muted">
              {row.label}
            </span>
            <span className="h-1.5 flex-1 rounded-full bg-ink-strong/5 overflow-hidden">
              <span
                className="block h-full rounded-full bg-gradient-to-r from-sky-soft to-brand"
                style={{ width: `${row.share}%` }}
              />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function HeroVisual() {
  const reduceMotion = useReducedMotion();
  const [videoFailed, setVideoFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  /*
   * A React `onError` prop is not enough here. The <video> is server-rendered, so the
   * browser starts fetching before hydration; if the CDN is unreachable the `error` event
   * fires and is gone before React attaches its handler — and media errors do not bubble,
   * so there is nothing to catch late. Check the element's own state on mount, then listen
   * for any failure that happens afterwards.
   */
  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;

    const fail = () => setVideoFailed(true);
    if (el.error) {
      fail();
      return;
    }
    el.addEventListener("error", fail);

    /*
     * Deferred fetch. Measured, `preload="metadata"` + autoPlay made the video the LCP
     * element outright on a fast link, and on ~1.6 Mbps it stole enough bandwidth from
     * the CSS and fonts to push the headline's LCP to 3.28s. Nothing decorative may gate
     * LCP (plan §5), so the video fetches only once the page has loaded and the main
     * thread is idle. The wrapper reserves the 1:1 box, so this costs no layout shift.
     */
    let cancelled = false;
    const start = () => {
      const v = videoRef.current;
      if (cancelled || !v) return;
      v.preload = "auto";
      v.load();
      void v.play().catch(() => {
        /* Autoplay refused — the poster-less first frame still shows once loaded. */
      });
    };
    const schedule = () =>
      typeof window.requestIdleCallback === "function"
        ? window.requestIdleCallback(start, { timeout: 2000 })
        : window.setTimeout(start, 200);

    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });

    return () => {
      cancelled = true;
      el.removeEventListener("error", fail);
      window.removeEventListener("load", schedule);
    };
  }, []);

  return (
    <motion.div
      initial={reduceMotion ? false : { y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: DURATION.reveal, ease: EASE_ENTRANCE, delay: 0.2 }}
      aria-hidden="true"
      className="relative w-full flex items-center justify-center lg:justify-end py-10 pointer-events-none"
    >
      <div className="relative w-full max-w-[600px]">
        <div
          className="absolute top-[30%] left-[20%] w-[420px] h-[420px] bg-sky-400/15 rounded-full blur-aura-md animate-pulse"
          style={{ animationDuration: "7000ms" }}
        />

        <svg
          viewBox="0 0 620 620"
          className="absolute w-[620px] h-[620px] top-1/2 left-1/2 -translate-x-1/2 -translate-y-[52%] opacity-35"
        >
          <defs>
            <linearGradient id="orbit-ring" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--color-sky-soft)" />
              <stop offset="100%" stopColor="var(--color-sky-vivid)" />
            </linearGradient>
          </defs>
          <circle
            cx="310"
            cy="310"
            r="304"
            fill="none"
            stroke="url(#orbit-ring)"
            strokeWidth="1"
            strokeDasharray="6 10"
          />
          <circle
            cx="310"
            cy="310"
            r="242"
            fill="none"
            stroke="url(#orbit-ring)"
            strokeWidth="1"
            strokeDasharray="2 9"
          />
          <circle cx="310" cy="310" r="178" fill="none" stroke="url(#orbit-ring)" strokeWidth="1" />
        </svg>

        <div className="relative">
          {videoFailed ? (
            <motion.div
              className="mx-4 sm:mx-10 md:mx-16"
              animate={reduceMotion ? undefined : { y: [0, -6, 0] }}
              transition={{ duration: 6.4, ease: EASE_FLOAT, repeat: Infinity }}
            >
              <PreviewPanel />
            </motion.div>
          ) : (
            <video
              ref={videoRef}
              src={HERO_VIDEO}
              loop
              muted
              playsInline
              controls={false}
              /* No autoPlay and no preload: the effect above starts it after load. */
              preload="none"
              onError={() => setVideoFailed(true)}
              /*
               * The blend that drops the clip's white backdrop into the page lives in
               * globals.css as `.hero-robot`, because it has to differ per theme and an
               * inline style cannot. `multiply` carries the light theme; the dark theme
               * inverts the clip first and screens it, since multiply over a dark canvas
               * would leave a dark robot on dark ground. See the rule for the full note.
               */
              className="hero-robot w-full aspect-square rounded-panel select-none block"
            />
          )}

          {BADGES.map((spec) => (
            <FloatingBadge key={spec.primary} spec={spec} safe={videoFailed} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
