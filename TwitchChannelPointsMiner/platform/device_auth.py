"""Start/stop background device-login jobs for dashboard."""

import json
import subprocess
import sys
import time
from pathlib import Path

from TwitchChannelPointsMiner.platform.auth_state import read_auth_state, write_auth_state
from TwitchChannelPointsMiner.platform.paths import COOKIES_DIR, ROOT, VAR_DIR, ensure_dirs

AUTH_JOBS_FILE = VAR_DIR / "auth_jobs.json"


def _read_jobs() -> dict:
    ensure_dirs()
    if not AUTH_JOBS_FILE.exists():
        return {}
    try:
        return json.loads(AUTH_JOBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_jobs(jobs: dict) -> None:
    ensure_dirs()
    AUTH_JOBS_FILE.write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _pid_running(pid: int) -> bool:
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        return False


def start_device_auth(username: str, force: bool = False) -> dict:
    username = username.strip()
    cookie = COOKIES_DIR / f"{username}.pkl"
    if force and cookie.exists():
        cookie.unlink()
        from TwitchChannelPointsMiner.platform.auth_state import clear_auth_state
        from TwitchChannelPointsMiner.platform.twitch_gql import invalidate_twitch

        clear_auth_state(username)
        invalidate_twitch(username)
    elif cookie.exists():
        write_auth_state(username, {"status": "complete"})
        return {"status": "complete", "already_authenticated": True}

    jobs = _read_jobs()
    job = jobs.get(username, {})
    pid = int(job.get("pid") or 0)
    if pid and _pid_running(pid):
        state = read_auth_state(username) or {"status": "starting"}
        return {"status": state.get("status", "starting"), "pid": pid}

    write_auth_state(username, {"status": "starting"})
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "device_auth_runner.py"),
        "--username",
        username,
    ]
    proc = subprocess.Popen(cmd, cwd=str(ROOT))
    jobs[username] = {"pid": proc.pid, "startedAt": int(time.time())}
    _write_jobs(jobs)
    return {"status": "starting", "pid": proc.pid}


def get_device_auth_status(username: str) -> dict:
    username = username.strip()
    cookie = COOKIES_DIR / f"{username}.pkl"
    if cookie.exists():
        return {
            "status": "complete",
            "user_code": None,
            "verification_uri": "https://www.twitch.tv/activate",
        }

    jobs = _read_jobs()
    job = jobs.get(username, {})
    pid = int(job.get("pid") or 0)
    if pid and not _pid_running(pid):
        jobs.pop(username, None)
        _write_jobs(jobs)

    state = read_auth_state(username) or {"status": "idle"}
    return {
        "status": state.get("status", "idle"),
        "user_code": state.get("user_code"),
        "verification_uri": state.get(
            "verification_uri", "https://www.twitch.tv/activate"
        ),
        "expires_in": state.get("expires_in"),
        "message": state.get("message"),
        "updated_at": state.get("updated_at"),
    }


def cancel_device_auth(username: str) -> None:
    username = username.strip()
    jobs = _read_jobs()
    job = jobs.pop(username, None)
    _write_jobs(jobs)
    if job:
        pid = int(job.get("pid") or 0)
        if pid and _pid_running(pid):
            import os
            import signal

            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
