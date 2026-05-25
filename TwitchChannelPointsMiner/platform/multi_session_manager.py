"""Run multiple bot miners in one OS process (threads). State driven by var/sessions.json."""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.account_store import get_account_config
from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.miner_factory import create_miner_from_config
from TwitchChannelPointsMiner.platform.miner_streamer_sync import sync_streamers_to_miner
from TwitchChannelPointsMiner.platform.paths import (
    COOKIES_DIR,
    ROOT,
    SESSIONS_FILE,
    STATUS_DIR,
    ensure_dirs,
)
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner
from TwitchChannelPointsMiner.platform.twitch_gql import invalidate_twitch

logger = logging.getLogger(__name__)

RECONCILE_INTERVAL_SEC = 5.0
STATUS_INTERVAL_SEC = 15.0
MANAGER_PID_FILE = ROOT / "var" / "multi_session.pid"


@dataclass
class _AccountWorker:
    username: str
    thread: threading.Thread
    stop_event: threading.Event = field(default_factory=threading.Event)
    miner: Any = None
    started_at: int = 0
    last_error: str | None = None


def _read_sessions_file() -> dict[str, dict]:
    ensure_dirs()
    if not SESSIONS_FILE.exists():
        return {}
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return dict(data.get("sessions") or {})
    except Exception:
        return {}


def _write_manager_pid(pid: int) -> None:
    ensure_dirs()
    MANAGER_PID_FILE.write_text(str(pid), encoding="utf-8")


def _clear_manager_pid() -> None:
    if MANAGER_PID_FILE.exists():
        MANAGER_PID_FILE.unlink(missing_ok=True)


def manager_pid_running() -> int | None:
    if not MANAGER_PID_FILE.exists():
        return None
    try:
        pid = int(MANAGER_PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    import psutil

    if psutil.pid_exists(pid):
        try:
            p = psutil.Process(pid)
            cmd = " ".join(p.cmdline()).lower()
            if "multi_session_runner" in cmd:
                return pid
        except Exception:
            pass
    return None


class MultiSessionManager:
    def __init__(self) -> None:
        self._workers: dict[str, _AccountWorker] = {}
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._streamers: list = []

    def _account_ready(self, username: str) -> str | None:
        if not get_account_config(username):
            return "missing_json_config"
        if not (COOKIES_DIR / f"{username}.pkl").exists():
            return "missing_cookie"
        return None

    def _miner_loop(self, username: str, stop: threading.Event) -> None:
        worker = self._workers.get(username)
        try:
            cfg = get_account_config(username)
            if not cfg:
                raise RuntimeError("no config in accounts.json")
            miner = create_miner_from_config(username, cfg)
            if worker:
                worker.miner = miner
            streamers = self._streamers or streamers_for_miner()
            if not streamers:
                raise RuntimeError("no streamers in config/streamers.json")

            log_event("info", "session", f"Майнер {username} стартует (multi)", account=username)

            status_stop = threading.Event()

            def status_loop() -> None:
                ensure_dirs()
                path = STATUS_DIR / f"{username}.json"
                prev: dict[str, int] = {}
                stop_flag = STATUS_DIR / f"{username}.stop"
                while not status_stop.is_set() and not stop.is_set():
                    if stop_flag.exists():
                        try:
                            stop_flag.unlink(missing_ok=True)
                        except Exception:
                            pass
                        try:
                            miner.end(0, 0)
                        except Exception:
                            miner.running = False
                            if getattr(miner, "twitch", None):
                                miner.twitch.running = False
                        status_stop.set()
                        return
                    try:
                        if getattr(miner, "running", False) and getattr(
                            miner, "streamers", None
                        ):
                            payload_streamers = []
                            for s in miner.streamers:
                                login = s.username
                                pts = int(s.channel_points or 0)
                                payload_streamers.append(
                                    {
                                        "login": login,
                                        "channel_points": pts,
                                        "is_online": bool(s.is_online),
                                    }
                                )
                                old = prev.get(login)
                                if old is not None and pts > old:
                                    log_event(
                                        "success",
                                        "points",
                                        f"{username} +{pts - old} на {login}",
                                        account=username,
                                        streamer=login,
                                    )
                                prev[login] = pts
                            path.write_text(
                                json.dumps(
                                    {
                                        "username": username,
                                        "updated_at": int(time.time()),
                                        "streamers": payload_streamers,
                                        "mode": "multi",
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                encoding="utf-8",
                            )
                        sync_streamers_to_miner(miner, username)
                    except Exception:
                        pass
                    status_stop.wait(STATUS_INTERVAL_SEC)

            threading.Thread(target=status_loop, daemon=True).start()

            miner.mine(streamers, followers=False)
            status_stop.set()
            log_event("warning", "session", f"Майнер {username} остановлен", account=username)
        except Exception as e:
            if worker:
                worker.last_error = str(e)
            log_event("error", "session", f"Майнер {username}: {e}", account=username)
            logger.exception("miner thread %s failed", username)
        finally:
            invalidate_twitch(username)
            with self._lock:
                self._workers.pop(username, None)

    def start_account(self, username: str) -> str | None:
        username = username.strip()
        reason = self._account_ready(username)
        if reason:
            return reason
        with self._lock:
            if username in self._workers and self._workers[username].thread.is_alive():
                return None
            stop_ev = threading.Event()
            thread = threading.Thread(
                target=self._miner_loop,
                args=(username, stop_ev),
                name=f"miner-{username}",
                daemon=True,
            )
            self._workers[username] = _AccountWorker(
                username=username,
                thread=thread,
                stop_event=stop_ev,
                started_at=int(time.time()),
            )
            thread.start()
        return None

    def stop_account(self, username: str) -> None:
        username = username.strip()
        with self._lock:
            w = self._workers.get(username)
        if not w:
            return
        w.stop_event.set()
        flag = STATUS_DIR / f"{username}.stop"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(str(int(time.time())), encoding="utf-8")
        w.thread.join(timeout=25)
        invalidate_twitch(username)

    def reconcile(self, desired: dict[str, dict]) -> None:
        desired_names = set(desired.keys())
        with self._lock:
            running = set(self._workers.keys())
        for username in desired_names - running:
            err = self.start_account(username)
            if err:
                log_event(
                    "warning",
                    "session",
                    f"Не запущен {username}: {err}",
                    account=username,
                )
        for username in running - desired_names:
            self.stop_account(username)

    def run_forever(self) -> None:
        self._streamers = streamers_for_miner()
        if not self._streamers:
            logger.error("No streamers configured — multi session manager exiting")
            return

        _write_manager_pid(__import__("os").getpid())

        def handle_signal(signum, frame):
            self._shutdown.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handle_signal)
            except (ValueError, OSError):
                pass

        log_event("info", "session", "Multi-session manager запущен")
        try:
            while not self._shutdown.is_set():
                desired = _read_sessions_file()
                self.reconcile(desired)
                time.sleep(RECONCILE_INTERVAL_SEC)
        finally:
            with self._lock:
                names = list(self._workers.keys())
            for name in names:
                self.stop_account(name)
            _clear_manager_pid()
            log_event("info", "session", "Multi-session manager завершён")

    def active_usernames(self) -> list[str]:
        with self._lock:
            return [
                u
                for u, w in self._workers.items()
                if w.thread.is_alive()
            ]
