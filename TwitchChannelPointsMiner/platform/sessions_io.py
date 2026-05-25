"""Atomic read/write for var/sessions.json (desired multi-session state)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.paths import SESSIONS_FILE, ensure_dirs

_sessions_lock = threading.Lock()


def read_sessions_file() -> dict[str, dict]:
    """Load desired bot sessions from disk."""
    ensure_dirs()
    with _sessions_lock:
        if not SESSIONS_FILE.exists():
            return {}
        try:
            raw = SESSIONS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
            sessions = data.get("sessions") if isinstance(data, dict) else {}
            return dict(sessions) if isinstance(sessions, dict) else {}
        except Exception:
            return {}


def write_sessions_file(sessions: dict[str, dict]) -> None:
    """Atomic write: temp file in same directory, then os.replace."""
    ensure_dirs()
    payload: dict[str, Any] = {"sessions": sessions}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with _sessions_lock:
        parent = SESSIONS_FILE.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".sessions.",
            suffix=".tmp",
            dir=str(parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, SESSIONS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
