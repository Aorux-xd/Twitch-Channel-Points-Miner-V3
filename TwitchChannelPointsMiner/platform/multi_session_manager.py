"""Multi-bot session manager: one OS process, reconcile desired vs running workers."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from TwitchChannelPointsMiner.platform.account_store import get_account_config
from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.miner_factory import create_miner_from_config
from TwitchChannelPointsMiner.platform.miner_streamer_sync import sync_streamers_to_miner
from TwitchChannelPointsMiner.platform.paths import (
    COOKIES_DIR,
    LOGS_DIR,
    ROOT,
    SESSIONS_FILE,
    STATUS_DIR,
    VAR_DIR,
    ensure_dirs,
)
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner
from TwitchChannelPointsMiner.platform.twitch_gql import invalidate_twitch

logger = logging.getLogger(__name__)

RECONCILE_INTERVAL_SEC = 6.0
STATUS_INTERVAL_SEC = 15.0
MANAGER_PID_FILE = VAR_DIR / "multi_session.pid"
STATE_FILE = VAR_DIR / "multi_session_state.json"
SESSION_LOG_DIR = LOGS_DIR / "sessions"
STOP_JOIN_TIMEOUT_SEC = 30.0


class WorkerState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class _AccountWorker:
    username: str
    thread: threading.Thread
    stop_event: threading.Event = field(default_factory=threading.Event)
    state: WorkerState = WorkerState.STARTING
    miner: Any = None
    started_at: int = 0
    last_error: str | None = None


def read_desired_sessions() -> dict[str, dict]:
    """Desired bots from var/sessions.json (never cleared by manager death)."""
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

    if not psutil.pid_exists(pid):
        return None
    try:
        cmd = " ".join(psutil.Process(pid).cmdline()).lower()
        if "multi_session_runner" in cmd:
            return pid
    except Exception:
        return None
    return None


def _setup_runner_logging() -> None:
    ensure_dirs()
    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    manager_log = LOGS_DIR / "multi_session_runner.log"
    if not any(
        getattr(h, "baseFilename", None) == str(manager_log) for h in root.handlers
    ):
        fh = logging.handlers.RotatingFileHandler(
            manager_log,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(fh)


def _bot_logger(username: str) -> logging.Logger:
    ensure_dirs()
    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    bot = logging.getLogger(f"miner.{username}")
    log_path = SESSION_LOG_DIR / f"{username}.log"
    if not any(
        getattr(h, "baseFilename", None) == str(log_path) for h in bot.handlers
    ):
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=1_500_000,
            backupCount=2,
            encoding="utf-8",
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        bot.addHandler(fh)
        bot.setLevel(logging.INFO)
        bot.propagate = True
    return bot


class MultiSessionManager:
    def __init__(self) -> None:
        self._workers: dict[str, _AccountWorker] = {}
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._streamers: list = []
        self._reconcile_errors: dict[str, str] = {}

    def _account_ready(self, username: str) -> str | None:
        if not get_account_config(username):
            return "missing_json_config"
        if not (COOKIES_DIR / f"{username}.pkl").exists():
            return "missing_cookie"
        return None

    def _publish_state(self) -> None:
        with self._lock:
            workers = {}
            for u, w in self._workers.items():
                workers[u] = {
                    "state": w.state.value,
                    "thread_alive": w.thread.is_alive(),
                    "started_at": w.started_at,
                    "last_error": w.last_error,
                }
            errors = dict(self._reconcile_errors)
        desired = read_desired_sessions()
        payload = {
            "manager_pid": os.getpid(),
            "manager_alive": True,
            "updated_at": int(time.time()),
            "desired": list(desired.keys()),
            "desired_count": len(desired),
            "running_count": sum(
                1 for w in workers.values() if w.get("thread_alive")
            ),
            "workers": workers,
            "reconcile_errors": errors,
        }
        ensure_dirs()
        STATE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _miner_loop(self, username: str, stop: threading.Event) -> None:
        bot_log = _bot_logger(username)
        worker: _AccountWorker | None = None
        with self._lock:
            worker = self._workers.get(username)
            if worker:
                worker.state = WorkerState.STARTING
        self._publish_state()

        try:
            cfg = get_account_config(username)
            if not cfg:
                raise RuntimeError("нет записи в config/accounts.json")
            miner = create_miner_from_config(username, cfg)
            with self._lock:
                w = self._workers.get(username)
                if w:
                    w.miner = miner
                    w.state = WorkerState.RUNNING
            self._publish_state()

            streamers = self._streamers or streamers_for_miner()
            if not streamers:
                raise RuntimeError("config/streamers.json пуст")

            bot_log.info("miner start")
            log_event("info", "session", f"Майнер {username} стартует", account=username)

            status_stop = threading.Event()

            def status_loop() -> None:
                path = STATUS_DIR / f"{username}.json"
                prev: dict[str, int] = {}
                stop_flag = STATUS_DIR / f"{username}.stop"
                while not status_stop.is_set() and not stop.is_set():
                    if stop_flag.exists() or self._shutdown.is_set():
                        try:
                            stop_flag.unlink(missing_ok=True)
                        except Exception:
                            pass
                        bot_log.info("stop requested")
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
                    except Exception as e:
                        bot_log.debug("status tick: %s", e)
                    status_stop.wait(STATUS_INTERVAL_SEC)

            threading.Thread(
                target=status_loop, name=f"status-{username}", daemon=True
            ).start()

            miner.mine(streamers, followers=False)
            status_stop.set()
            bot_log.info("miner stopped normally")
            log_event("warning", "session", f"Майнер {username} остановлен", account=username)
        except Exception as e:
            bot_log.exception("miner failed: %s", e)
            with self._lock:
                w = self._workers.get(username)
                if w:
                    w.last_error = str(e)
                    w.state = WorkerState.ERROR
            log_event("error", "session", f"Майнер {username}: {e}", account=username)
        finally:
            invalidate_twitch(username)
            with self._lock:
                w = self._workers.pop(username, None)
                if w:
                    w.state = WorkerState.STOPPED
            self._publish_state()

    def start_account(self, username: str) -> str | None:
        username = username.strip()
        reason = self._account_ready(username)
        if reason:
            self._reconcile_errors[username] = reason
            return reason
        self._reconcile_errors.pop(username, None)

        with self._lock:
            existing = self._workers.get(username)
            if existing and existing.thread.is_alive():
                return None
            if existing and not existing.thread.is_alive():
                self._workers.pop(username, None)

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
                state=WorkerState.STARTING,
                started_at=int(time.time()),
            )
            thread.start()
        log_event("info", "session", f"Запуск потока {username}", account=username)
        self._publish_state()
        return None

    def stop_account(self, username: str, *, graceful: bool = True) -> None:
        username = username.strip()
        with self._lock:
            w = self._workers.get(username)
        if not w:
            return
        w.state = WorkerState.STOPPING
        self._publish_state()
        w.stop_event.set()
        flag = STATUS_DIR / f"{username}.stop"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(str(int(time.time())), encoding="utf-8")
        if graceful:
            w.thread.join(timeout=STOP_JOIN_TIMEOUT_SEC)
        invalidate_twitch(username)
        with self._lock:
            if not w.thread.is_alive():
                self._workers.pop(username, None)
        self._publish_state()
        log_event("warning", "session", f"Поток {username} остановлен", account=username)

    def _prune_dead_workers(self) -> None:
        with self._lock:
            dead = [u for u, w in self._workers.items() if not w.thread.is_alive()]
            for u in dead:
                w = self._workers.pop(u)
                if w.state not in (WorkerState.ERROR, WorkerState.STOPPED):
                    w.state = WorkerState.STOPPED

    def reconcile(self, desired: dict[str, dict]) -> dict[str, str]:
        """Sync running worker threads with desired session keys."""
        self._prune_dead_workers()
        desired_names = set(desired.keys())
        with self._lock:
            running = {
                u
                for u, w in self._workers.items()
                if w.thread.is_alive()
            }

        actions: dict[str, str] = {}

        for username in sorted(desired_names - running):
            err = self.start_account(username)
            if err:
                actions[username] = f"start_failed:{err}"
            else:
                actions[username] = "started"

        for username in sorted(running - desired_names):
            self.stop_account(username)
            actions[username] = "stopped"

        self._publish_state()
        return actions

    def shutdown_all(self) -> None:
        log_event("info", "session", "Graceful shutdown всех ботов")
        with self._lock:
            names = list(self._workers.keys())
        for name in names:
            self.stop_account(name)
        self._publish_state()

    def run_forever(self) -> None:
        _setup_runner_logging()
        self._streamers = streamers_for_miner()
        if not self._streamers:
            logger.error("Нет стримеров в config/streamers.json")
            sys.exit(2)

        _write_manager_pid(os.getpid())

        def handle_signal(signum, frame):
            logger.info("Signal %s — shutdown", signum)
            self._shutdown.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handle_signal)
            except (ValueError, OSError):
                pass

        log_event("info", "session", "Multi-session runner запущен (reconcile loop)")
        logger.info(
            "Reconcile every %ss — desired state: %s",
            RECONCILE_INTERVAL_SEC,
            SESSIONS_FILE,
        )
        try:
            while not self._shutdown.is_set():
                desired = read_desired_sessions()
                actions = self.reconcile(desired)
                if actions:
                    logger.info("reconcile: %s", actions)
                time.sleep(RECONCILE_INTERVAL_SEC)
        finally:
            self.shutdown_all()
            _clear_manager_pid()
            if STATE_FILE.exists():
                try:
                    stale = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                    stale["manager_alive"] = False
                    stale["updated_at"] = int(time.time())
                    STATE_FILE.write_text(
                        json.dumps(stale, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    STATE_FILE.unlink(missing_ok=True)
            log_event("info", "session", "Multi-session runner завершён")

    def debug_snapshot(self) -> dict:
        with self._lock:
            workers = {
                u: {
                    "state": w.state.value,
                    "thread_alive": w.thread.is_alive(),
                    "started_at": w.started_at,
                    "last_error": w.last_error,
                }
                for u, w in self._workers.items()
            }
        desired = read_desired_sessions()
        return {
            "manager_pid": manager_pid_running() or os.getpid(),
            "desired": desired,
            "workers": workers,
            "reconcile_errors": dict(self._reconcile_errors),
        }


def get_runtime_state() -> dict:
    """Read last published state (for API when runner is separate process)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    desired = read_desired_sessions()
    pid = manager_pid_running()
    return {
        "manager_pid": pid,
        "manager_alive": pid is not None,
        "desired": list(desired.keys()),
        "desired_count": len(desired),
        "running_count": 0,
        "workers": {},
        "reconcile_errors": {},
    }
