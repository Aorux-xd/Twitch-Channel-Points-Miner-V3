"""Simple per-key rate limiting for chat and reward activation."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, min_interval_sec: float):
        self._interval = max(0.0, float(min_interval_sec))
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, key: str) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = time.time()
            prev = self._last.get(key, 0.0)
            delay = self._interval - (now - prev)
            if delay > 0:
                time.sleep(delay)
            self._last[key] = time.time()


# Global limiters used by panel API paths
CHAT_SEND_LIMITER = RateLimiter(0.85)
REDEEM_LIMITER = RateLimiter(1.0)
GQL_LIMITER = RateLimiter(0.35)
