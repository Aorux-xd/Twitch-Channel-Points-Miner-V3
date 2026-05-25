"""Session control API — desired state in var/sessions.json, enforced by multi_session_runner."""

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
    get_runtime_state,
    manager_pid_running,
    read_desired_sessions,
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
MANAGER_START_SLEEP = 2.5


def _python_executable() -> str:
    venv_py = ROOT / "venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


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
        proc.wait(timeout=8)
    except psutil.NoSuchProcess:
        pass
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def load_sessions() -> dict:
    """Desired bots (what the panel asked to run). Not cleared when runner restarts."""
    return read_desired_sessions()


def active_worker_usernames() -> set[str]:
    """Usernames with alive miner threads according to last runner state snapshot."""
    state = get_runtime_state()
    workers = state.get("workers") or {}
    return {
        u
        for u, meta in workers.items()
        if meta.get("thread_alive")
        and meta.get("state") in ("running", "starting")
    }


def sessions_debug() -> dict:
    """Full picture for /api/sessions/debug."""
    desired = read_desired_sessions()
    runtime = get_runtime_state()
    active = active_worker_usernames()
    return {
        "manager_pid": manager_pid_running(),
        "manager_alive": manager_pid_running() is not None,
        "desired_sessions": desired,
        "desired_count": len(desired),
        "active_workers": sorted(active),
        "active_count": len(active),
        "orphan_desired": sorted(set(desired) - active),
        "orphan_running": sorted(active - set(desired)),
        "runtime": runtime,
    }


def multi_runner_system_stats() -> dict:
    state = get_runtime_state()
    return {
        "multi_session_runner_alive": manager_pid_running() is not None,
        "multi_session_pid": manager_pid_running(),
        "desired_bots": state.get("desired_count", 0),
        "running_bots": state.get("running_count", 0),
        "reconcile_errors": state.get("reconcile_errors") or {},
    }


def _save_sessions(sessions: dict) -> None:
    _write_json(SESSIONS_FILE, {"sessions": sessions})


def _ensure_multi_manager() -> bool:
    if manager_pid_running():
        return True
    if not MULTI_SESSION_RUNNER.is_file():
        return False
    py = _python_executable()
    log_path = ROOT / "logs" / "multi_session_runner.log"
    try:
        log_f = open(log_path, "a", encoding="utf-8")
        subprocess.Popen(
            [py, str(MULTI_SESSION_RUNNER)],
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_f.close()
    except Exception:
        subprocess.Popen(
            [py, str(MULTI_SESSION_RUNNER)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    time.sleep(MANAGER_START_SLEEP)
    return manager_pid_running() is not None


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

    sessions = read_desired_sessions()
    started = []
    skipped = []

    for username in usernames:
        if username in sessions:
            skipped.append({"username": username, "reason": "already_in_desired"})
            continue
        reason = _account_can_start(username)
        if reason:
            skipped.append({"username": username, "reason": reason})
            continue
        sessions[username] = {
            "startedAt": int(time.time()),
            "mode": "multi",
        }
        started.append({"username": username, "mode": "multi"})

    if started:
        _save_sessions(sessions)
        manager_ok = _ensure_multi_manager()
        if not manager_ok:
            for row in started:
                skipped.append(
                    {
                        "username": row["username"],
                        "reason": "multi_manager_start_failed",
                    }
                )
            started = []
        for row in started:
            log_event(
                "info",
                "session",
                f"Бот {row['username']} в desired — reconcile запустит поток",
                account=row["username"],
            )

    return {"started": started, "skipped": skipped}


def stop_sessions(usernames: list[str]) -> dict:
    from TwitchChannelPointsMiner.platform.twitch_gql import invalidate_twitch

    usernames = [str(u).strip() for u in usernames if str(u).strip()]
    sessions = read_desired_sessions()
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
        log_event("warning", "session", f"Бот {username} снят с desired", account=username)

    _save_sessions(sessions)

    if not sessions and manager_pid_running():
        _kill_pid(manager_pid_running())

    return {"stopped": stopped, "missing": missing}


def restart_sessions(usernames: list[str]) -> dict:
    """Re-auth / config refresh: remove from desired, stop, re-add, reconcile starts thread."""
    usernames = [str(u).strip() for u in usernames if str(u).strip()]
    stop_sessions(usernames)
    time.sleep(2.0)
    return start_sessions(usernames)
