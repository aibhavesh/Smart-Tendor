import type { ReactNode } from "react";

/*
 * Cards and panels. The glass treatment is the landing page's signature, carried
 * inward so the app reads as the same surface as the front door.
 */

const GLASS =
  "bg-gradient-to-br from-surface/75 to-surface/45 border border-surface/70 ring-1 ring-ink-strong/5 backdrop-blur-glass";

export function Card({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return (
    <Tag className={`${GLASS} shadow-glass rounded-panel p-6 ${className ?? ""}`}>{children}</Tag>
  );
}

/** The raised centrepiece treatment — heavier glow. Use sparingly, once per screen. */
export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={`${GLASS} shadow-panel rounded-panel p-6 ${className ?? ""}`}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex items-start justify-between gap-4 mb-5">
      <div className="min-w-0">
        <h2 className="font-outfit font-bold text-ui-lg tracking-tight text-ink">{title}</h2>
        {description ? <p className="text-caption text-ink-muted mt-1">{description}</p> : null}
      </div>
      {actions ? <div className="shrink-0 flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** Compact label/value pair used across detail screens. */
export function DataRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 border-b border-ink-strong/5 last:border-0">
      <span className="text-caption text-ink-muted shrink-0">{label}</span>
      <span className="text-ui text-ink text-right min-w-0">{children}</span>
    </div>
  );
}
