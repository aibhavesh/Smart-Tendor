"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";

/*
 * Light/dark switch. Sits in all three chromes — the landing Navbar, the signed-in
 * AppShell header and the AuthLayout header — so it is reachable from every screen.
 *
 * The icon shows the theme you would GET, not the one you are in, which is the
 * convention every OS switch uses: a moon means "go dark".
 *
 * No mounted flag: useTheme resolves to "light" on the server and to the reader's
 * real theme once hydrated, so React swaps the icon on its own.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const label = dark ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={`h-9 w-9 rounded-control border border-ink-strong/10 bg-ink-strong/5 hover:bg-ink-strong/10 flex items-center justify-center text-ink-strong transition-colors ${className}`}
    >
      {dark ? (
        <Sun className="w-4 h-4" aria-hidden="true" />
      ) : (
        <Moon className="w-4 h-4" aria-hidden="true" />
      )}
    </button>
  );
}
