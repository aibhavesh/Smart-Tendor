import { API_BASE } from "./api";

/*
 * Frontend log shipping (plan §8 / FR-705).
 *
 * Browser diagnostics are posted to POST /observability/logs, which re-emits them through
 * the server's structured logger so client and server problems land in one pipeline.
 *
 * Four things this must not do:
 *   - Retry a disabled feature. The endpoint 404s when ENABLE_FRONTEND_LOGS is off; that
 *     is a configuration answer, not a transient error, so the client shuts itself off.
 *   - Recurse. A failure while shipping logs must never itself be logged.
 *   - Lose the last batch. The interesting entries are usually the ones just before the
 *     user navigates away, so the page-hide flush uses `keepalive`.
 *   - Block anything. Every failure path is swallowed; telemetry is never worth an error.
 */

type Level = "debug" | "info" | "warning" | "error";

interface Entry {
  level: Level;
  message: string;
  context?: Record<string, unknown> | null;
  url?: string | null;
  timestamp?: string | null;
}

/** Server accepts 1..100 entries per batch; stay clear of the ceiling. */
const MAX_BATCH = 50;
/** Bound the queue so a failing endpoint cannot grow it without limit. */
const MAX_QUEUE = 200;
const FLUSH_INTERVAL_MS = 10_000;
const MAX_MESSAGE = 2000;

let queue: Entry[] = [];
let disabled = false;
let installed = false;
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight = false;

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

async function send(batch: Entry[], keepalive = false): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/observability/logs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ logs: batch }),
      keepalive,
    });

    // 404 means the feature is switched off server-side. Stop for good.
    if (res.status === 404) {
      disabled = true;
      queue = [];
      if (timer) clearInterval(timer);
      timer = null;
    }

    /*
     * 429 is deliberately NOT handled. The endpoint is rate-limited per client
     * (it accepts anonymous callers, so that is what keeps it from being an open
     * write sink), but the ceiling sits well above this client's own maximum —
     * 50 entries per 10s. Reaching it means something is looping, and the batch
     * being dropped is the correct outcome. Re-queueing would amplify it.
     */
  } catch {
    // Never surface, never retry-storm, never log about logging.
  }
}

export function flushLogs(keepalive = false): void {
  if (disabled || inFlight || queue.length === 0) return;
  const batch = queue.slice(0, MAX_BATCH);
  queue = queue.slice(batch.length);
  inFlight = true;
  void send(batch, keepalive).finally(() => {
    inFlight = false;
  });
}

export function logEvent(
  level: Level,
  message: string,
  context?: Record<string, unknown>,
): void {
  if (disabled || typeof window === "undefined") return;
  if (!message) return;

  queue.push({
    level,
    message: truncate(message, MAX_MESSAGE),
    context: context ?? null,
    url: truncate(window.location.href, 2000),
    timestamp: new Date().toISOString(),
  });

  // Drop the oldest rather than grow without bound if the endpoint is unreachable.
  if (queue.length > MAX_QUEUE) queue = queue.slice(queue.length - MAX_QUEUE);
  if (queue.length >= MAX_BATCH) flushLogs();
}

/** Install global handlers and the periodic flush. Idempotent. */
export function installTelemetry(): () => void {
  if (installed || typeof window === "undefined") return () => {};
  installed = true;

  const onError = (event: ErrorEvent) => {
    logEvent("error", event.message || "window.onerror", {
      source: event.filename,
      line: event.lineno,
      column: event.colno,
      stack: event.error instanceof Error ? event.error.stack?.slice(0, 1000) : undefined,
    });
  };

  const onRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    logEvent("error", reason instanceof Error ? reason.message : String(reason), {
      kind: "unhandledrejection",
      stack: reason instanceof Error ? reason.stack?.slice(0, 1000) : undefined,
    });
  };

  // `visibilitychange` fires on mobile backgrounding where `beforeunload` does not.
  const onHide = () => {
    if (document.visibilityState === "hidden") flushLogs(true);
  };

  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  document.addEventListener("visibilitychange", onHide);
  window.addEventListener("pagehide", () => flushLogs(true));

  timer = setInterval(() => flushLogs(), FLUSH_INTERVAL_MS);

  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
    document.removeEventListener("visibilitychange", onHide);
    if (timer) clearInterval(timer);
    timer = null;
    installed = false;
  };
}

/** Test seam — lets a check assert the disabled-on-404 behaviour. */
export function __telemetryState() {
  return { disabled, queued: queue.length };
}
