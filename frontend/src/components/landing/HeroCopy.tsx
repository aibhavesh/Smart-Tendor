"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ChevronRight, ScrollText } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { EASE_ENTRANCE, DURATION } from "@/lib/motion";


/*
 * Left column. The prompt's composition is kept — proof capsule, display heading, body
 * paragraph, primary CTA — with copy written for the actual product rather than the
 * prompt's "Assist." assistant. The prompt's ghost CTA beside the primary is dropped:
 * sign-in is reachable from the register screen, and one target keeps the ask singular.
 *
 * The prompt's avatar collage and "Trusted by 10,000+ users worldwide" line are
 * deliberately absent: there is no such user base, and the Unsplash portraits would
 * have presented real people as customers. The capsule instead states something the
 * API can actually back — every recommendation carries its `applied_rules` trail.
 */
export function HeroCopy() {
  const reduceMotion = useReducedMotion();

  /*
   * Signed in, the CTA is not an invitation to sign up — it is the way into the work, so
   * it opens the screen that takes a tender and its document.
   *
   * "loading" keeps the sign-in target: it is the safe guess for a first-time visitor,
   * and a signed-in reader landing on /login is one click from where they meant to be.
   * There is no separate sign-up — the first Google sign-in creates the account.
   */
  const { status } = useAuth();
  const ctaHref = status === "authenticated" ? "/tenders/upload" : "/login";

  return (
    <motion.div
      initial={reduceMotion ? false : { y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: DURATION.reveal, ease: EASE_ENTRANCE, delay: 0.1 }}
      className="flex flex-col justify-center items-start text-left max-w-[620px] lg:pr-6"
    >
      <div className="px-3 py-1.5 rounded-full bg-ink-strong/5 border border-ink-strong/5 flex items-center gap-3 w-fit shadow-xs">
        <ScrollText className="w-4 h-4 text-brand shrink-0" aria-hidden="true" />
        <span className="text-caption text-ink-strong/80">
          Every answer comes with{" "}
          <span className="font-semibold text-ink">the reasons behind it</span>
        </span>
      </div>

      <h1 className="font-outfit font-black text-display-sm sm:text-display-md lg:text-display-lg leading-display tracking-tight lg:tracking-display mt-6 select-none text-ink-strong">
        {/* Breaks are explicit: at 60px in a 5-of-12 column the first line wraps on its
            own, so leaving it to reflow makes the rhythm width-dependent. */}
        Know which
        <br />
        tenders to
        <br />
        bid on.
      </h1>

      <p className="text-lead text-ink-strong/60 tracking-body leading-relaxed mt-5 max-w-[480px]">
        Upload a tender document and it gets read for you: what is being asked for, where the
        risk sits, and whether your past projects qualify you — ending in a clear bid or
        don&apos;t bid answer you can explain to anyone.
      </p>

      {/* Still a flex row with one child: it keeps the motion wrapper shrink-to-fit, so
          the hover scale pivots on the button rather than a full-width box. */}
      <div className="mt-8 flex items-center">
        <motion.div whileHover={reduceMotion ? undefined : { scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Link
            href={ctaHref}
            /* leading-5 restores the 20px line-height that Tailwind's own `text-sm`
               carried. The --text-* tokens set font-size only, matching the arbitrary
               text-[Npx] values they replaced, so a size swapped off a built-in scale
               has to bring its line-height with it. */
            className="group bg-brand-hover hover:bg-brand-deep text-white pl-6 pr-2 py-2 rounded-surface flex items-center gap-4 text-ui leading-5 font-bold transition-all w-fit shadow-cta"
          >
            Start analyzing
            <span className="w-8 h-8 rounded-full bg-surface flex items-center justify-center text-brand-hover transition-transform group-hover:translate-x-1">
              <ChevronRight className="w-4 h-4" aria-hidden="true" />
            </span>
          </Link>
        </motion.div>
      </div>
    </motion.div>
  );
}
