import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.paths import ROOT, SESSIONS_FILE, STATUS_DIR, ensure_dirs

SESSION_RUNNER = ROOT / "session_runner.py"

SCREEN_NAME_RE = re.compile(r"^twitch\d+$")
SCREEN_LINE_RE = re.compile(r"^\s*\d+\.(\S+)\s+\(")
SCREEN_START_SLEEP = 1.2


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


def _write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _screen_available() -> bool:
    if os.name == "nt":
        return False
    try:
        subprocess.run(
            ["screen", "-v"],
            capture_output=True,
            check=False,
            timeout=3,
        )
        return True
    except Exception:
        return False


def _screen_list() -> list[tuple[str, str]]:
    """Parse screen -ls like legacy manager.py."""
    sessions = []
    try:
        output = subprocess.check_output(
            ["screen", "-ls"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except Exception:
        return sessions
    for line in output.splitlines():
        if ".twitch" not in line:
            continue
        if "Detached" not in line and "Attached" not in line:
            continue
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        sess_id = parts[0] if "." in parts[0] else parts[1]
        if "." not in sess_id:
            continue
        name = sess_id.split(".", 1)[1].split()[0]
        status = next((p for p in parts if "(" in p), "(Unknown)").strip("()")
        sessions.append((name, status))
    return sessions


def _allocate_screen_name(sessions: dict) -> str:
    used = {
        str(m.get("screen"))
        for m in sessions.values()
        if m.get("screen") and SCREEN_NAME_RE.match(str(m.get("screen")))
    }
    running = {name for name, _ in _screen_list()}
    used |= running
    n = 1
    while f"twitch{n}" in used:
        n += 1
    return f"twitch{n}"


def _screen_session_exists(name: str) -> bool:
    return any(n == name for n, _ in _screen_list())


def _quit_screen(name: str) -> None:
    if not name:
        return
    subprocess.run(
        ["screen", "-S", name, "-X", "quit"],
        capture_output=True,
        check=False,
        timeout=5,
        cwd=str(ROOT),
    )


def _start_screen_session(name: str, *program_args: str) -> bool:
    """
    Legacy manager.py pattern (one process per screen):
      screen -dmS twitch1 venv/bin/python session_runner.py --username bot
    Config lives in accounts/<bot>.py — not a second copy under run_panel/.
    """
    py = _python_executable()
    cmd = ["screen", "-dmS", name, py, *program_args]
    try:
        subprocess.run(cmd, cwd=str(ROOT), check=True, timeout=15)
        time.sleep(SCREEN_START_SLEEP)
        return _screen_session_exists(name)
    except Exception:
        return False


def _kill_process_tree(pid: int):
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
        for child in children:
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


def _runner_pids(username: str) -> list[int]:
    """Find miner processes for account."""
    pids = []
    safe = username.lower()
    needle = f"--username {safe}"
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            joined = " ".join(str(x) for x in cmdline).lower()
            if "session_runner.py" in joined and needle in joined:
                pids.append(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def _pid_is_running(pid: int) -> bool:
    try:
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        return False


def load_sessions() -> dict:
    ensure_dirs()
    data = _read_json(SESSIONS_FILE, {"sessions": {}})
    sessions = data.get("sessions", {})
    changed = False
    for username, meta in list(sessions.items()):
        screen = meta.get("screen")
        pid = int(meta.get("pid") or 0)
        alive = False
        if screen and _screen_session_exists(screen):
            alive = True
        elif pid and _pid_is_running(pid):
            alive = True
        elif _runner_pids(username):
            alive = True
        if not alive:
            sessions.pop(username, None)
            changed = True
    if changed:
        _save_sessions(sessions)
    return sessions


def _save_sessions(sessions: dict):
    _write_json(SESSIONS_FILE, {"sessions": sessions})


def start_sessions(usernames: list[str]) -> dict:
    from TwitchChannelPointsMiner.platform.paths import ACCOUNTS_DIR
    from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner

    usernames = [str(u).strip() for u in usernames if str(u).strip()]
    sessions = load_sessions()
    started = []
    skipped = []

    use_screen = _screen_available()
    streamers = streamers_for_miner()
    if not streamers:
        return {
            "started": [],
            "skipped": [
                {
                    "username": u,
                    "reason": "no_streamers_configured",
                }
                for u in usernames
            ],
        }

    for username in usernames:
        if username in sessions:
            skipped.append({"username": username, "reason": "already_running"})
            continue
        account_file = ACCOUNTS_DIR / f"{username}.py"
        if not account_file.exists():
            skipped.append({"username": username, "reason": "missing_account_config"})
            continue

        if not SESSION_RUNNER.is_file():
            skipped.append({"username": username, "reason": "session_runner_missing"})
            continue

        runner_args = (str(SESSION_RUNNER), "--username", username)
        screen_name = None
        if use_screen:
            screen_name = _allocate_screen_name(sessions)
            if _screen_session_exists(screen_name):
                skipped.append({"username": username, "reason": "screen_name_taken"})
                continue

            ok = _start_screen_session(screen_name, *runner_args)
            if not ok:
                _quit_screen(screen_name)
                skipped.append({"username": username, "reason": "screen_start_failed"})
                log_event(
                    "error",
                    "session",
                    f"Не удалось запустить {username} в screen {screen_name}",
                    account=username,
                )
                continue

            pids = _runner_pids(username)
            runner_pid = max(pids) if pids else 0
            meta = {
                "pid": runner_pid,
                "startedAt": int(time.time()),
                "screen": screen_name,
            }
            sessions[username] = meta
            started.append(
                {
                    "username": username,
                    "pid": runner_pid,
                    "screen": screen_name,
                }
            )
            log_event(
                "info",
                "session",
                f"Сессия {username} запущена (screen {screen_name})",
                account=username,
            )
        else:
            py = _python_executable()
            proc = subprocess.Popen(
                [py, *runner_args],
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            time.sleep(SCREEN_START_SLEEP)
            if not _pid_is_running(proc.pid):
                skipped.append({"username": username, "reason": "runner_exit_early"})
                log_event(
                    "error",
                    "session",
                    f"Сессия {username} завершилась сразу после запуска",
                    account=username,
                )
                continue
            meta = {
                "pid": proc.pid,
                "startedAt": int(time.time()),
            }
            sessions[username] = meta
            started.append(
                {
                    "username": username,
                    "pid": proc.pid,
                    "screen": None,
                }
            )
            log_event(
                "info",
                "session",
                f"Сессия {username} запущена (pid {proc.pid})",
                account=username,
            )

    _save_sessions(sessions)
    return {"started": started, "skipped": skipped}


def stop_sessions(usernames: list[str]) -> dict:
    usernames = [str(u).strip() for u in usernames if str(u).strip()]
    sessions = load_sessions()
    stopped = []
    missing = []

    from TwitchChannelPointsMiner.platform.twitch_gql import drop_twitch_client

    for username in usernames:
        meta = sessions.get(username) or {}
        pid = int(meta.get("pid") or 0)
        screen_name = meta.get("screen")

        stop_flag = STATUS_DIR / f"{username}.stop"
        stop_flag.parent.mkdir(parents=True, exist_ok=True)
        stop_flag.write_text(str(int(time.time())), encoding="utf-8")

        if screen_name:
            _quit_screen(screen_name)
            time.sleep(0.5)
            if _screen_session_exists(screen_name):
                _quit_screen(screen_name)

        targets = set(_runner_pids(username))
        if pid:
            targets.add(pid)

        if not meta and not targets and not screen_name:
            missing.append(username)
            if stop_flag.exists():
                stop_flag.unlink(missing_ok=True)
            continue

        for target_pid in targets:
            _kill_process_tree(target_pid)

        time.sleep(1.5)
        for target_pid in list(targets):
            if _pid_is_running(target_pid):
                _kill_process_tree(target_pid)

        if stop_flag.exists():
            stop_flag.unlink(missing_ok=True)

        drop_twitch_client(username)
        sessions.pop(username, None)
        stopped.append(username)
        log_event(
            "warning",
            "session",
            f"Бот {username} остановлен"
            + (f" (screen {screen_name})" if screen_name else ""),
            account=username,
        )

    _save_sessions(sessions)
    return {"stopped": stopped, "missing": missing}
