import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Fustat, Inter, Outfit } from "next/font/google";
import "./globals.css";
import { BRAND_NAME } from "@/components/brand/Wordmark";
import { Providers } from "./providers";
import { THEME_STORAGE_KEY } from "@/lib/theme-key";

/*
 * All three faces are variable fonts, so no `weight` is declared — the full
 * range the prompt asks for (Outfit 400–900, Fustat 500–800, Inter 400–700)
 * comes from the variable axis. next/font self-hosts these at build time.
 */
const inter = Inter({ subsets: ["latin"], variable: "--ff-inter", display: "swap" });
const outfit = Outfit({ subsets: ["latin"], variable: "--ff-outfit", display: "swap" });
const fustat = Fustat({ subsets: ["latin"], variable: "--ff-fustat", display: "swap" });

export const metadata: Metadata = {
  // Company first, product second: the tab and any shared link lead with the name on
  // the wordmark, and "Tender Intelligence" stays on as the descriptor.
  title: `${BRAND_NAME} — Tender Intelligence`,
  description:
    "Extract the BOQ, score the risk, check qualification, and get a GO or NO_BID verdict with the rule trail behind it.",
};

/*
 * Runs before first paint, ahead of React, so the correct palette is on <html>
 * from the very first frame. Without it every dark-theme reader gets a white
 * flash on each navigation, because the server can only ever render "light".
 *
 * Deliberately tiny and dependency-free — it is inlined into the document head
 * and blocks paint. The key must stay in step with THEME_STORAGE_KEY.
 */
const THEME_BOOTSTRAP = `(function(){try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");var d=s==="dark"||(s===null&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light";}catch(e){document.documentElement.dataset.theme="light";}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    /*
     * suppressHydrationWarning: the script above mutates data-theme before React
     * hydrates, so the server's markup and the live DOM legitimately differ on
     * this one attribute. The warning is the mechanism working, not a fault.
     */
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${outfit.variable} ${fustat.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body className="min-h-full flex flex-col bg-canvas font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
