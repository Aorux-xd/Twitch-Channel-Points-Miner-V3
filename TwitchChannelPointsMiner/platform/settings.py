"""Unified settings loader (config/settings.json)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.paths import CONFIG_DIR, ensure_dirs

SETTINGS_FILE = CONFIG_DIR / "settings.json"
_LEGACY_RATE_LIMITS = CONFIG_DIR / "rate_limits.json"

_DEFAULTS: dict[str, Any] = {
    "rate_limits": {
        "chat_send_sec": 0.85,
        "redeem_sec": 1.0,
        "gql_sec": 0.35,
    },
    "cache_ttl_sec": {
        "streamers_meta": 180,
        "points": 120,
        "rewards": 900,
        "offline_max": 604800,
    },
    "runner": {
        "reconcile_interval_sec": 5,
        "max_restart_attempts": 3,
        "max_concurrent_restarts": 3,
        "restart_backoff_sec": [5, 15, 45],
        "heartbeat_interval_sec": 10,
        "status_interval_sec": 15,
        "watchdog_interval_sec": 30,
        "error_history_size": 5,
    },
    "background_refresh_interval_sec": 90,
    "log_rotation": {"max_bytes": 5_242_880, "backup_count": 5},
    "logging": {"manager_level": "INFO", "bot_level": "INFO"},
    "gql": {"request_timeout_sec": 20, "persisted_fallback": True},
    "chat": {"buffer_limit": 150, "bulk_queue_max": 32, "dedupe_window_sec": 3.0},
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _load_raw() -> dict[str, Any]:
    ensure_dirs()
    data: dict[str, Any] = {}
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    elif _LEGACY_RATE_LIMITS.exists():
        try:
            legacy = json.loads(_LEGACY_RATE_LIMITS.read_text(encoding="utf-8"))
            if isinstance(legacy, dict):
                data["rate_limits"] = legacy
        except Exception:
            pass
    return _deep_merge(_DEFAULTS, data)


def get_settings(*, reload: bool = False) -> dict[str, Any]:
    global _cache
    with _lock:
        if reload or _cache is None:
            _cache = _load_raw()
        return _cache


def get_section(name: str) -> dict[str, Any]:
    section = get_settings().get(name)
    return section if isinstance(section, dict) else {}


def reload_settings() -> dict[str, Any]:
    return get_settings(reload=True)
