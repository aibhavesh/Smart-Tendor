import type { ReactNode } from "react";
import { Wordmark } from "@/components/brand/Wordmark";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

/*
 * The auth seam.
 *
 * Plan §8: these screens carry the landing page's visual weight deliberately — the CTA
 * lands here, and it should feel like the same surface rather than a hand-off to a
 * different product. Same canvas, same aura, same glass, same faces.
 */
export function AuthLayout({
  title,
  lede,
  children,
  footer,
}: {
  title: string;
  lede?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="relative flex-1 overflow-x-clip bg-canvas flex flex-col">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-[10%] left-[8%] w-[560px] h-[560px] rounded-full bg-sky-soft/20 blur-aura-lg" />
        <div className="absolute top-[18%] -right-[6%] w-[620px] h-[620px] rounded-full bg-sky-vivid/20 blur-aura-lg" />
      </div>

      <header className="relative w-full max-w-[1280px] mx-auto px-6 sm:px-12 lg:px-20 pt-8 flex items-center justify-between gap-4">
        <Wordmark className="inline-flex text-wordmark" />
        <ThemeToggle />
      </header>

      <main className="relative flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[440px]">
          <h1 className="font-outfit font-black text-display-sm leading-display tracking-tight text-ink-strong">
            {title}
          </h1>
          {lede ? (
            <p className="text-ui text-ink-strong/60 tracking-body leading-relaxed mt-3">{lede}</p>
          ) : null}

          <div className="mt-7 rounded-panel border border-surface/70 ring-1 ring-ink-strong/5 bg-gradient-to-br from-surface/75 to-surface/45 backdrop-blur-glass shadow-panel p-6 sm:p-7">
            {children}
          </div>

          {footer ? <div className="mt-5 text-caption text-ink-strong/60">{footer}</div> : null}
        </div>
      </main>
    </div>
  );
}
