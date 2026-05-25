"""JSON-backed bot account configs (replaces per-bot accounts/*.py generation)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.paths import ACCOUNTS_DIR, CONFIG_DIR, ensure_dirs

logger = logging.getLogger(__name__)

ACCOUNTS_JSON = CONFIG_DIR / "accounts.json"

DEFAULT_ACCOUNT_CONFIG = {
    "claim_drops_startup": False,
    "priority_streak": True,
    "priority_drops": True,
    "priority_order": True,
    "make_predictions": True,
    "follow_raid": True,
    "claim_drops": True,
    "claim_moments": True,
    "watch_streak": True,
    "chat_presence": "ONLINE",
    "bet_strategy": "SMART",
    "bet_percentage": 5,
    "bet_max_points": 50000,
    "save_logs": True,
    "less_logs": False,
}


def _load_store() -> dict[str, dict[str, Any]]:
    ensure_dirs()
    if not ACCOUNTS_JSON.exists():
        return {}
    try:
        raw = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
        accounts = raw.get("accounts") if isinstance(raw, dict) else raw
        if not isinstance(accounts, dict):
            return {}
        return {str(k): dict(v) for k, v in accounts.items() if isinstance(v, dict)}
    except Exception as e:
        logger.warning("accounts.json read failed: %s", e)
        return {}


def _save_store(accounts: dict[str, dict[str, Any]]) -> None:
    ensure_dirs()
    ACCOUNTS_JSON.write_text(
        json.dumps({"accounts": accounts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_configured_usernames() -> list[str]:
    return sorted(_load_store().keys())


def get_account_config(username: str) -> dict[str, Any] | None:
    username = username.strip()
    row = _load_store().get(username)
    if row:
        return {**DEFAULT_ACCOUNT_CONFIG, **row, "username": username}
    return None


def save_account_config(username: str, config: dict[str, Any]) -> dict[str, Any]:
    username = username.strip()
    store = _load_store()
    merged = {**DEFAULT_ACCOUNT_CONFIG, **config, "username": username}
    store[username] = {k: v for k, v in merged.items() if k != "username"}
    _save_store(store)
    return merged


def delete_account_config(username: str) -> None:
    store = _load_store()
    store.pop(username.strip(), None)
    _save_store(store)


def migrate_py_accounts_to_json() -> int:
    """One-time import: accounts/*.py -> config/accounts.json (keeps .py as fallback)."""
    imported = 0
    store = _load_store()
    for py in ACCOUNTS_DIR.glob("*.py"):
        if py.name.startswith("_"):
            continue
        username = py.stem
        if username in store:
            continue
        store[username] = dict(DEFAULT_ACCOUNT_CONFIG)
        imported += 1
    if imported:
        _save_store(store)
        logger.info("Migrated %s account(s) from .py stubs to accounts.json", imported)
    return imported
