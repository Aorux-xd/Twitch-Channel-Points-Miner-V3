"""Runtime state for Twitch device-login (TV activate code) shown in the dashboard."""

import json
import time
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.paths import VAR_DIR, ensure_dirs

AUTH_DIR = VAR_DIR / "auth"


def auth_file(username: str) -> Path:
    return AUTH_DIR / f"{username.strip()}.json"


def write_auth_state(username: str, data: dict[str, Any]) -> None:
    ensure_dirs()
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    payload = {**data, "username": username.strip(), "updated_at": int(time.time())}
    auth_file(username).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_auth_state(username: str) -> dict[str, Any] | None:
    path = auth_file(username)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_auth_state(username: str) -> None:
    path = auth_file(username)
    if path.exists():
        path.unlink()
