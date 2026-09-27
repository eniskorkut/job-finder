"""Process local sliding window rate limiter.

Deliberately dependency free: phase 1 runs as a single localhost process. When
the app grows past one worker this can be swapped for Redis without touching
the call sites.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def check(self, key: str) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)`` without recording a hit."""
        now = time.monotonic()
        with self._lock:
            events = self._prune(key, now)
            if len(events) < self.max_attempts:
                return True, 0
            retry_after = max(1, int(self.window_seconds - (now - events[0])) + 1)
            return False, retry_after

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._prune(key, now)
            events.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limit exceeded, retry in {retry_after}s")
        self.retry_after = retry_after
