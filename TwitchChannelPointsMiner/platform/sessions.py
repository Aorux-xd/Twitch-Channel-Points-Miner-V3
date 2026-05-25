"""Bot session control — V3.1: one multi_session_runner process, state in var/sessions.json."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

from TwitchChannelPointsMiner.platform.account_store import get_account_config
from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.multi_session_manager import (
    manager_pid_running,
)
from TwitchChannelPointsMiner.platform.paths import (
    COOKIES_DIR,
    ROOT,
    SESSIONS_FILE,
    STATUS_DIR,
    ensure_dirs,
)
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner

MULTI_SESSION_RUNNER = ROOT / "multi_session_runner.py"
MANAGER_START_SLEEP = 2.0


def _python_executable() -> str:
    venv_py = ROOT / "venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _kill_pid(pid: int) -> None:
    if not pid:
        return
    try:
        proc = psutil.Process(pid)
        for child in proc.children(recursive=True):
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        proc.kill()
        proc.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def load_sessions() -> dict:
    """Active bots declared in sessions.json while multi manager is alive."""
    ensure_dirs()
    data = _read_json(SESSIONS_FILE, {"sessions": {}})
    sessions = dict(data.get("sessions") or {})
    if not manager_pid_running():
        if sessions:
            _write_json(SESSIONS_FILE, {"sessions": {}})
        return {}
    return sessions


def _save_sessions(sessions: dict) -> None:
    _write_json(SESSIONS_FILE, {"sessions": sessions})


def _ensure_multi_manager() -> bool:
    if manager_pid_running():
        return True
    if not MULTI_SESSION_RUNNER.is_file():
        return False
    py = _python_executable()
    try:
        proc = subprocess.Popen(
            [py, str(MULTI_SESSION_RUNNER)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(MANAGER_START_SLEEP)
        if manager_pid_running():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(1.0)
        return manager_pid_running() is not None
    except Exception:
        return False


def _account_can_start(username: str) -> str | None:
    if not get_account_config(username):
        return "missing_json_config"
    if not (COOKIES_DIR / f"{username}.pkl").exists():
        return "missing_cookie"
    return None


def start_sessions(usernames: list[str]) -> dict:
    usernames = [str(u).strip() for u in usernames if str(u).strip()]
    if not streamers_for_miner():
        return {
            "started": [],
            "skipped": [
                {"username": u, "reason": "no_streamers_configured"} for u in usernames
            ],
        }

    if not _ensure_multi_manager():
        return {
            "started": [],
            "skipped": [
                {"username": u, "reason": "multi_manager_start_failed"}
                for u in usernames
            ],
        }

    sessions = _read_json(SESSIONS_FILE, {"sessions": {}}).get("sessions") or {}
    started = []
    skipped = []

    for username in usernames:
        if username in sessions:
            skipped.append({"username": username, "reason": "already_running"})
            continue
        reason = _account_can_start(username)
        if reason:
            skipped.append({"username": username, "reason": reason})
            continue
        sessions[username] = {
            "startedAt": int(time.time()),
            "mode": "multi",
            "pid": manager_pid_running(),
        }
        started.append(
            {
                "username": username,
                "pid": manager_pid_running(),
                "mode": "multi",
            }
        )
        log_event(
            "info",
            "session",
            f"Сессия {username} поставлена в очередь (multi-process)",
            account=username,
        )

    _save_sessions(sessions)
    return {"started": started, "skipped": skipped}


def stop_sessions(usernames: list[str]) -> dict:
    from TwitchChannelPointsMiner.platform.twitch_gql import invalidate_twitch

    usernames = [str(u).strip() for u in usernames if str(u).strip()]
    data = _read_json(SESSIONS_FILE, {"sessions": {}})
    sessions = dict(data.get("sessions") or {})
    stopped = []
    missing = []

    for username in usernames:
        if username not in sessions:
            missing.append(username)
        else:
            sessions.pop(username, None)
            stopped.append(username)

        stop_flag = STATUS_DIR / f"{username}.stop"
        stop_flag.parent.mkdir(parents=True, exist_ok=True)
        stop_flag.write_text(str(int(time.time())), encoding="utf-8")
        invalidate_twitch(username)
        log_event("warning", "session", f"Бот {username} остановлен", account=username)

    _save_sessions(sessions)

    if not sessions and manager_pid_running():
        pid = manager_pid_running()
        if pid:
            _kill_pid(pid)

    return {"stopped": stopped, "missing": missing}


def restart_sessions(usernames: list[str]) -> dict:
    """Stop then start (used after force re-auth)."""
    stop_sessions(usernames)
    time.sleep(2.0)
    return start_sessions(usernames)
