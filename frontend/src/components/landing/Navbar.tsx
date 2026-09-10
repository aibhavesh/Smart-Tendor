"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, ChevronDown, History, LogOut, Menu, UserRound, X } from "lucide-react";
import { Wordmark } from "@/components/brand/Wordmark";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { useAuth } from "@/lib/auth";
import { EASE_ENTRANCE, DURATION } from "@/lib/motion";

// Assembled rather than written as "#features": the theme lint rule reads the leading
// "#fea" as a hex colour, so the hash is kept out of the string literal.
const FEATURES_ID = "features";

const NAV_LINKS = [
  { label: "Home", href: "#home" },
  { label: "Features", href: `#${FEATURES_ID}` },
] as const;

/*
 * "My history" is the tender list. GET /tenders takes limit/offset/status/search and no
 * owner filter, so this is everything the reader may see rather than only their own
 * uploads — narrowing it honestly needs the endpoint to grow the filter first.
 */
const ACCOUNT_LINKS = [
  { label: "My history", href: "/tenders", icon: History },
  { label: "My profile", href: "/profile", icon: UserRound },
] as const;

function AccountMenu({ name }: { name: string }) {
  const reduceMotion = useReducedMotion();
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative hidden sm:block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="h-9 pl-3 pr-3.5 rounded-control bg-ink-strong/5 hover:bg-ink-strong/10 border border-ink-strong/10 text-ui font-semibold flex items-center gap-2 text-ink-strong transition-all hover:shadow-md"
      >
        <span className="w-6 h-6 rounded-full bg-brand/10 flex items-center justify-center shrink-0">
          <UserRound className="w-3.5 h-3.5 text-brand-ink" aria-hidden="true" />
        </span>
        {/* A long full name would otherwise push the nav row out of shape. */}
        <span className="max-w-[160px] truncate">{name}</span>
        <ChevronDown
          className={`w-3.5 h-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            role="menu"
            aria-label="Account"
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
            transition={{ duration: DURATION.quick, ease: EASE_ENTRANCE }}
            className="absolute right-0 top-[calc(100%+8px)] w-[200px] p-1.5 rounded-surface border border-ink-strong/10 bg-surface/95 backdrop-blur-drawer shadow-panel flex flex-col"
          >
            {ACCOUNT_LINKS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="h-9 px-3 rounded-control text-ui font-medium text-ink-strong/80 hover:text-ink-strong hover:bg-ink-strong/5 flex items-center gap-2.5 transition-colors"
              >
                <item.icon className="w-4 h-4 text-brand-ink shrink-0" aria-hidden="true" />
                {item.label}
              </Link>
            ))}

            <span className="h-px mx-1 my-1 bg-ink-strong/10" aria-hidden="true" />

            {/*
             * No navigation afterwards: logout flips auth status to anonymous, this menu
             * unmounts with it and the bar swaps back to Sign in / Get started. The reader
             * stays on the page they were reading, which is the right place to be left.
             */}
            <button
              type="button"
              role="menuitem"
              disabled={signingOut}
              onClick={() => {
                setSigningOut(true);
                void logout();
              }}
              className="h-9 px-3 rounded-control text-ui font-medium text-ink-strong/80 hover:text-state-danger-ink hover:bg-state-danger/10 disabled:opacity-60 flex items-center gap-2.5 transition-colors text-left"
            >
              <LogOut className="w-4 h-4 shrink-0" aria-hidden="true" />
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export function Navbar() {
  const reduceMotion = useReducedMotion();
  const [menuOpen, setMenuOpen] = useState(false);

  /*
   * Someone arriving here from inside the app already has an account, so offering them
   * "Get started" is noise. `status` is "loading" until the persisted refresh token has
   * been exchanged, and that slot stays empty until it resolves — a signed-in visitor
   * seeing "Sign in" flash before it swaps would be worse than a beat of nothing.
   */
  const { status, user, logout } = useAuth();

  // Close the drawer on Escape, and stop the page scrolling behind it.
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [menuOpen]);

  return (
    <motion.header
      initial={reduceMotion ? false : { y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: DURATION.entrance, ease: EASE_ENTRANCE }}
      className="fixed top-[30px] left-0 right-0 z-50 flex justify-center px-4 pointer-events-none"
    >
      <nav
        aria-label="Main"
        className="w-full max-w-[1280px] h-12 rounded-surface pointer-events-auto transition-all duration-300"
      >
        {/* Padding tracks <main>'s so the logo sits flush with the hero headline. */}
        <div className="flex items-center justify-between gap-8 px-6 sm:px-12 lg:px-20 py-2 w-full">
          <Wordmark className="flex text-wordmark" />

          <ul className="hidden md:flex items-center gap-8">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className="text-ui font-medium text-ink-strong/60 hover:text-ink-strong transition-colors"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-2">
            <ThemeToggle />

            {status === "authenticated" ? (
              <AccountMenu name={user?.full_name || "Account"} />
            ) : status === "anonymous" ? (
              <>
                {/* Both routes lead to /login now: signing in with a work Google account
                    IS the sign-up, so offering two destinations would imply a choice
                    that does not exist. */}
                <Link
                  href="/login"
                  className="h-9 px-4 rounded-control text-ui font-semibold hidden sm:flex items-center text-ink-strong/60 hover:text-ink-strong hover:bg-ink-strong/5 transition-colors"
                >
                  Sign in
                </Link>

                <Link
                  href="/login"
                  className="group h-9 px-5 rounded-control bg-ink-strong/5 hover:bg-ink-strong/10 border border-ink-strong/10 text-ui font-semibold hidden sm:flex items-center gap-2 text-ink-strong transition-all hover:shadow-md"
                >
                  Get started
                  <ArrowRight
                    className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </Link>
              </>
            ) : null}

            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              aria-expanded={menuOpen}
              className="md:hidden h-9 w-9 rounded-control border border-ink-strong/10 bg-ink-strong/5 hover:bg-ink-strong/10 flex items-center justify-center text-ink-strong transition-colors"
            >
              <Menu className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </nav>

      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: DURATION.quick }}
              onClick={() => setMenuOpen(false)}
              className="fixed inset-0 z-40 bg-ink-strong/20 pointer-events-auto md:hidden"
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Menu"
              initial={reduceMotion ? { x: 0 } : { x: "100%" }}
              animate={{ x: 0 }}
              exit={reduceMotion ? { opacity: 0 } : { x: "100%" }}
              transition={{ duration: DURATION.drawer, ease: EASE_ENTRANCE }}
              className="fixed top-0 right-0 bottom-0 z-50 w-[260px] bg-surface/95 backdrop-blur-drawer border-l border-ink-strong/10 pointer-events-auto md:hidden flex flex-col"
            >
              <div className="flex items-center justify-end p-4">
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  aria-label="Close menu"
                  className="h-9 w-9 rounded-control border border-ink-strong/10 bg-ink-strong/5 hover:bg-ink-strong/10 flex items-center justify-center text-ink-strong transition-colors"
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>

              <ul className="flex flex-col px-6 gap-5">
                {NAV_LINKS.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      onClick={() => setMenuOpen(false)}
                      className="text-ui-lg font-medium text-ink-strong/70 hover:text-ink-strong transition-colors"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>

              {/* The header's links are hidden below sm, so the drawer carries them — and
                  the same signed-in/out split. */}
              <div className="mt-auto p-6 flex flex-col gap-3">
                {status === "authenticated" ? (
                  <>
                    {/* No dropdown down here — the drawer is already the disclosure, so
                        the same two destinations sit flat under the reader's name. */}
                    <p className="px-1 text-caption font-semibold text-ink-muted truncate">
                      {user?.full_name || "Account"}
                    </p>
                    {ACCOUNT_LINKS.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setMenuOpen(false)}
                        className="h-10 w-full rounded-control border border-ink-strong/10 bg-ink-strong/5 hover:bg-ink-strong/10 text-ink-strong text-ui font-semibold flex items-center justify-center gap-2 transition-colors"
                      >
                        <item.icon className="w-4 h-4 text-brand-ink" aria-hidden="true" />
                        {item.label}
                      </Link>
                    ))}

                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false);
                        void logout();
                      }}
                      className="h-10 w-full rounded-control text-state-danger-ink hover:bg-state-danger/10 text-ui font-semibold flex items-center justify-center gap-2 transition-colors"
                    >
                      <LogOut className="w-4 h-4" aria-hidden="true" />
                      Sign out
                    </button>
                  </>
                ) : status === "anonymous" ? (
                  <>
                    <Link
                      href="/login"
                      onClick={() => setMenuOpen(false)}
                      className="h-10 w-full rounded-control bg-brand-hover hover:bg-brand-deep text-white text-ui font-semibold flex items-center justify-center gap-2 transition-colors"
                    >
                      Get started
                      <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                    </Link>

                    <Link
                      href="/login"
                      onClick={() => setMenuOpen(false)}
                      className="h-10 w-full rounded-control border border-ink-strong/10 bg-ink-strong/5 hover:bg-ink-strong/10 text-ink-strong text-ui font-semibold flex items-center justify-center transition-colors"
                    >
                      Sign in
                    </Link>
                  </>
                ) : null}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
