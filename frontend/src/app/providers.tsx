"use client";

import { useEffect, type ReactNode } from "react";
import { AuthProvider } from "@/lib/auth";
import { installTelemetry } from "@/lib/telemetry";
import { ThemeProvider } from "@/lib/theme";

/**
 * Client providers for the whole tree.
 *
 * `children` is passed through untouched, so server components below stay server
 * components — the landing page is still statically prerendered.
 */
export function Providers({ children }: { children: ReactNode }) {
  // Frontend log shipping (FR-705). Installed once, for every screen including the
  // public ones — a crash on the landing page is exactly as worth capturing.
  useEffect(() => installTelemetry(), []);

  return (
    <ThemeProvider>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  );
}
