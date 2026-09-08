"use client";

import { useEffect, useState } from "react";
import { describeError } from "./api";

/*
 * Shared read hook.
 *
 * The fetching happens inside the effect and the loader passed in must not itself call
 * setState — React's set-state-in-effect rule traces setState through anything an effect
 * invokes, so a hoisted `load()` that sets state trips it however the awaits are ordered.
 *
 * `deps` is spread into the effect's dependency list; callers pass primitives (offset,
 * search, id), not objects, so an inline object literal cannot cause a refetch loop.
 */

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly (string | number | boolean | null | undefined)[],
  options: { context?: Partial<Record<number, string>>; enabled?: boolean } = {},
): Resource<T> {
  const { context, enabled = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      try {
        const next = await load(controller.signal);
        if (cancelled) return;
        setData(next);
        setError(null);
        setLoading(false);
      } catch (err) {
        // An aborted request is a superseded one, not a failure to report.
        if (cancelled || controller.signal.aborted) return;
        setError(describeError(err, context));
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
    // `load` and `context` are recreated each render by design; deps drive refetching.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadKey, enabled]);

  return { data, error, loading, reload: () => setReloadKey((k) => k + 1) };
}
