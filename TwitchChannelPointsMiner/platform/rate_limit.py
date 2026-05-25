"""Configurable per-key rate limiting (chat, redeem, GQL)."""

from __future__ import annotations

import threading
import time

from TwitchChannelPointsMiner.platform.settings import get_section, reload_settings

_lock = threading.Lock()
_limiters: dict[str, "RateLimiter"] = {}


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


def load_rate_limits() -> dict[str, float]:
    limits = get_section("rate_limits")
    return {
        "chat_send_sec": float(limits.get("chat_send_sec", 0.85)),
        "redeem_sec": float(limits.get("redeem_sec", 1.0)),
        "gql_sec": float(limits.get("gql_sec", 0.35)),
    }


def _get_limiter(name: str, config_key: str) -> RateLimiter:
    with _lock:
        if name not in _limiters:
            limits = load_rate_limits()
            _limiters[name] = RateLimiter(limits.get(config_key, 1.0))
        return _limiters[name]


def reload_limiters() -> None:
    reload_settings()
    with _lock:
        _limiters.clear()


class _GetLimiterProxy:
    def __init__(self, name: str, key: str) -> None:
        self._name = name
        self._key = key

    def wait(self, token: str) -> None:
        _get_limiter(self._name, self._key).wait(token)


CHAT_SEND_LIMITER = _GetLimiterProxy("chat", "chat_send_sec")
REDEEM_LIMITER = _GetLimiterProxy("redeem", "redeem_sec")
GQL_LIMITER = _GetLimiterProxy("gql", "gql_sec")
