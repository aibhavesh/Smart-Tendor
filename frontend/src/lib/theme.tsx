"use client";

import { useCallback, useEffect, useSyncExternalStore, type ReactNode } from "react";

import { THEME_STORAGE_KEY } from "./theme-key";

/*
 * Theme state.
 *
 * The palette itself lives entirely in globals.css, keyed off `data-theme` on
 * <html>. Nothing here knows a colour — this module only decides which of the
 * two words goes on the attribute, and remembers the answer.
 *
 * Resolution order, highest first:
 *   1. an explicit choice this browser has stored
 *   2. the operating system's prefers-color-scheme
 *   3. light
 *
 * A stored choice is a decision, so it keeps winning even if the OS later
 * changes. Someone who has never chosen keeps following the OS live.
 *
 * Modelled as an external store rather than component state, because that is
 * what it is: the truth lives in localStorage and matchMedia, both of which can
 * change without React's involvement — including from another tab. useSync-
 * ExternalStore also gives hydration the right shape, since `getServerSnapshot`
 * lets the server render "light" and the client correct it after hydrating,
 * with no mismatch and no mounted flag.
 */

export type Theme = "light" | "dark";

/**
 * Re-exported so client code has one import for everything theme-related. The
 * definition lives in a directive-free module because layout.tsx is a server
 * component and cannot read a value through a "use client" boundary.
 */
export { THEME_STORAGE_KEY };

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** Subscribers that only a setTheme() call can wake — storage events do not fire in the writing tab. */
const listeners = new Set<() => void>();

function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    // Private mode, or storage disabled entirely. Not worth failing a render over.
    return null;
  }
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  // Fired by *other* tabs, which is what keeps two open windows in agreement.
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    query.removeEventListener("change", onChange);
    window.removeEventListener("storage", onChange);
  };
}

function getSnapshot(): Theme {
  return storedTheme() ?? systemTheme();
}

/*
 * The server has no reader to ask. It renders light, and the client swaps to the
 * real answer on hydration — invisibly, because the pre-paint script in
 * layout.tsx already put the right palette on <html> before any of this ran.
 */
function getServerSnapshot(): Theme {
  return "light";
}

export function setTheme(next: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // The theme still applies for this session; it just will not be remembered.
  }
  listeners.forEach((notify) => notify());
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme]);
  return { theme, setTheme, toggle };
}

/**
 * Owns the one side effect: mirroring the resolved theme onto <html>, from a
 * single place rather than once per component that happens to read the theme.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return <>{children}</>;
}
