import json
import re
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.paths import ACCOUNTS_DIR, COOKIES_DIR, ensure_dirs

SAFE_USERNAME = re.compile(r"^[a-zA-Z0-9_]{3,25}$")


def account_schema() -> list[dict[str, Any]]:
    """Form fields mirrored from run.py miner configuration."""
    return [
        {"key": "username", "label": "Twitch логин", "type": "text", "required": True},
        {"key": "password", "label": "Пароль (опционально)", "type": "password", "required": False},
        {
            "key": "claim_drops_startup",
            "label": "Забрать дропы при старте",
            "type": "boolean",
            "default": False,
        },
        {
            "key": "priority_streak",
            "label": "Приоритет: Watch Streak",
            "type": "boolean",
            "default": True,
        },
        {
            "key": "priority_drops",
            "label": "Приоритет: Drops",
            "type": "boolean",
            "default": True,
        },
        {
            "key": "priority_order",
            "label": "Приоритет: порядок списка",
            "type": "boolean",
            "default": True,
        },
        {
            "key": "make_predictions",
            "label": "Делать предикты",
            "type": "boolean",
            "default": True,
        },
        {"key": "follow_raid", "label": "Следовать за рейдом", "type": "boolean", "default": True},
        {"key": "claim_drops", "label": "Собирать дропы", "type": "boolean", "default": True},
        {"key": "claim_moments", "label": "Собирать moments", "type": "boolean", "default": True},
        {"key": "watch_streak", "label": "Watch streak", "type": "boolean", "default": True},
        {
            "key": "chat_presence",
            "label": "IRC чат",
            "type": "select",
            "options": ["ONLINE", "OFFLINE", "ALWAYS", "NEVER"],
            "default": "ONLINE",
        },
        {
            "key": "bet_strategy",
            "label": "Стратегия ставок",
            "type": "select",
            "options": [
                "SMART",
                "HIGH_ODDS",
                "PERCENTAGE",
                "MOST_VOTED",
                "SMART_MONEY",
            ],
            "default": "SMART",
        },
        {"key": "bet_percentage", "label": "% баллов на ставку", "type": "number", "default": 5},
        {"key": "bet_max_points", "label": "Макс. баллов на ставку", "type": "number", "default": 50000},
        {"key": "save_logs", "label": "Сохранять логи в файл", "type": "boolean", "default": True},
        {"key": "less_logs", "label": "Короткие логи", "type": "boolean", "default": False},
    ]


def _all_usernames() -> set[str]:
    """Usernames from config/accounts.json and/or cookies."""
    from TwitchChannelPointsMiner.platform.account_store import list_configured_usernames

    names: set[str] = set(list_configured_usernames())
    for pkl in COOKIES_DIR.glob("*.pkl"):
        names.add(pkl.stem)
    return names


def list_account_usernames() -> list[str]:
    return sorted(_all_usernames())


def accounts_with_cookies(session: str | None = None) -> list[str]:
    """Bot accounts with .pkl — one session or all."""
    with_cookie = [
        u for u in list_account_usernames() if (COOKIES_DIR / f"{u}.pkl").exists()
    ]
    if not with_cookie:
        return []
    session = (session or "").strip()
    if not session or session in ("Все сессии", "__all__", "all"):
        return with_cookie
    if session in with_cookie:
        return [session]
    return []


def list_accounts(running: set[str] | None = None) -> list[dict]:
    ensure_dirs()
    running = running or set()
    accounts = []
    for username in sorted(_all_usernames()):
        from TwitchChannelPointsMiner.platform.account_store import get_account_config

        cookie = COOKIES_DIR / f"{username}.pkl"
        has_config = get_account_config(username) is not None
        accounts.append(
            {
                "username": username,
                "file": "config/accounts.json" if has_config else None,
                "has_config": has_config,
                "has_cookie": cookie.exists(),
                "status": "Active" if username in running else "Offline",
            }
        )
    return accounts


def create_account(config: dict[str, Any]) -> dict:
    from TwitchChannelPointsMiner.platform.account_store import (
        get_account_config,
        save_account_config,
    )

    username = str(config.get("username", "")).strip()
    if not SAFE_USERNAME.match(username):
        raise ValueError("Invalid Twitch username")

    ensure_dirs()
    if get_account_config(username):
        raise ValueError("Account already exists")
    cookie = COOKIES_DIR / f"{username}.pkl"
    if username in _all_usernames() and cookie.exists():
        save_account_config(username, {**config, "username": username})
        return {
            "username": username,
            "file": "config/accounts.json",
            "has_cookie": True,
            "has_config": True,
            "restored": True,
        }

    save_account_config(username, config)
    return {
        "username": username,
        "file": "config/accounts.json",
        "has_cookie": cookie.exists(),
        "has_config": True,
    }


def restore_account_config(username: str) -> dict:
    """Create JSON config with defaults when only cookie exists."""
    from TwitchChannelPointsMiner.platform.account_store import (
        get_account_config,
        save_account_config,
    )

    username = username.strip()
    if not SAFE_USERNAME.match(username):
        raise ValueError("Invalid Twitch username")
    cookie = COOKIES_DIR / f"{username}.pkl"
    if not cookie.exists():
        raise ValueError("No Twitch cookie for this account")
    if get_account_config(username):
        return {
            "username": username,
            "file": "config/accounts.json",
            "has_config": True,
            "restored": False,
        }
    save_account_config(username, {"username": username})
    return {
        "username": username,
        "file": "config/accounts.json",
        "has_config": True,
        "restored": True,
    }


def delete_account(username: str, remove_cookie: bool = True):
    username = username.strip()
    from TwitchChannelPointsMiner.platform.account_store import delete_account_config
    from TwitchChannelPointsMiner.platform.sessions import stop_sessions

    stop_sessions([username])
    delete_account_config(username)
    cookie = COOKIES_DIR / f"{username}.pkl"
    if remove_cookie and cookie.exists():
        cookie.unlink()
    from TwitchChannelPointsMiner.platform.auth_state import clear_auth_state

    clear_auth_state(username)
