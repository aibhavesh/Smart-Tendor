"""A small fixed-window rate limiter for unauthenticated write endpoints.

Deliberately in-process and dependency-free. Its limits are worth being honest
about, because they decide what this can and cannot be used for:

* **Per process.** Each worker keeps its own counters, so the effective limit
  across ``N`` workers is ``N * limit``. Set the limit with that in mind.
* **Not durable.** A restart forgets every window.
* **Not a security boundary.** It bounds the cost of abuse; it does not stop a
  determined attacker, who can rotate source addresses. Anything that must not
  be reachable by an anonymous caller needs authorisation, not a rate limit.

Good enough for keeping a log-ingestion endpoint from being turned into an
unbounded write amplifier. Reach for Redis if a real quota is ever needed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    """Allow at most ``limit`` units of cost per ``window_seconds`` per key."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float = 60.0,
        max_tracked_keys: int = 10_000,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_tracked = max_tracked_keys
        self._windows: dict[str, _Window] = {}

    def check(self, key: str, cost: int = 1) -> tuple[bool, int]:
        """Charge ``cost`` against ``key``.

        Returns ``(allowed, retry_after_seconds)``. When refused, nothing is
        charged — a caller that is already over the limit should not have its
        window extended by continuing to try.
        """
        if self._limit <= 0:
            return True, 0  # disabled

        now = time.monotonic()
        window = self._windows.get(key)

        if window is None or now - window.started_at >= self._window:
            # A fresh window still has to honour the limit. Skipping this check
            # would let a single oversized batch through unmetered every time a
            # window rolls over, which is exactly the case worth stopping.
            if cost > self._limit:
                return False, int(self._window) + 1
            self._prune(now)
            self._windows[key] = _Window(started_at=now, count=cost)
            return True, 0

        if window.count + cost > self._limit:
            retry_after = max(1, int(self._window - (now - window.started_at)) + 1)
            return False, retry_after

        window.count += cost
        return True, 0

    def _prune(self, now: float) -> None:
        """Drop expired windows, and cap the table if a flood creates new keys.

        Without the cap, one request per forged source address would grow this
        dictionary without bound — which is the very failure the limiter exists
        to prevent, just moved into memory.
        """
        if len(self._windows) < self._max_tracked:
            return

        self._windows = {
            key: w for key, w in self._windows.items() if now - w.started_at < self._window
        }
        if len(self._windows) >= self._max_tracked:
            # Still saturated with live windows: evict the oldest so recent
            # callers keep being counted.
            for key in sorted(self._windows, key=lambda k: self._windows[k].started_at)[
                : len(self._windows) // 2
            ]:
                del self._windows[key]
