import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { useEffect, type ComponentType, type ReactNode } from "react";
import { Button } from "./Button";
import { logEvent } from "@/lib/telemetry";

/*
 * Empty, loading and error states. Every list and detail surface needs all three
 * (plan §9 checklist item 7), so they are primitives rather than per-screen markup.
 */

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
}: {
  title: string;
  description?: string;
  icon?: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center text-center py-14 px-6">
      <span className="w-12 h-12 rounded-full bg-ink-strong/5 flex items-center justify-center">
        <Icon className="w-5 h-5 text-ink-muted" aria-hidden={true} />
      </span>
      <p className="font-outfit font-bold text-ui-lg text-ink mt-4">{title}</p>
      {description ? (
        <p className="text-caption text-ink-muted mt-1.5 max-w-[42ch]">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

/**
 * Error state. `detail` should be the mapped, specific message — a 404 on a tender and
 * a 409 on a duplicate tender number must not render the same words.
 */
export function ErrorState({
  title = "Something went wrong",
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  // Every error the user is actually shown is worth shipping — this is the one place
  // that reliably sees them, whatever screen produced it.
  useEffect(() => {
    logEvent("error", detail ? `${title}: ${detail}` : title, { surface: "ErrorState" });
  }, [title, detail]);

  return (
    <div className="flex flex-col items-center text-center py-14 px-6" role="alert">
      <span className="w-12 h-12 rounded-full bg-state-danger/10 flex items-center justify-center">
        <AlertTriangle className="w-5 h-5 text-state-danger-ink" aria-hidden={true} />
      </span>
      <p className="font-outfit font-bold text-ui-lg text-ink mt-4">{title}</p>
      {detail ? (
        <p className="text-caption text-ink-muted mt-1.5 max-w-[52ch]">{detail}</p>
      ) : null}
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-5" onClick={onRetry}>
          <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}

/** Loading placeholder. `aria-hidden` — announce loading via the container's aria-busy. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`block rounded-control bg-ink-strong/8 animate-pulse ${className ?? ""}`}
    />
  );
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-live="polite" className="flex flex-col gap-3 py-2">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
