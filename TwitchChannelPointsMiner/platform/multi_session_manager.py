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
from typing import Any, Callable

from TwitchChannelPointsMiner.platform.account_store import get_account_config
from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.miner_factory import create_miner_from_config
from TwitchChannelPointsMiner.platform.miner_streamer_sync import sync_streamers_to_miner
from TwitchChannelPointsMiner.platform.paths import (
    COOKIES_DIR,
    LOGS_DIR,
    SESSIONS_FILE,
    STATUS_DIR,
    VAR_DIR,
    ensure_dirs,
)
from TwitchChannelPointsMiner.platform.sessions_io import read_sessions_file
from TwitchChannelPointsMiner.platform.settings import get_section
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner
from TwitchChannelPointsMiner.platform.twitch_gql import invalidate_twitch

logger = logging.getLogger(__name__)

MANAGER_PID_FILE = VAR_DIR / "multi_session.pid"
STATE_FILE = VAR_DIR / "multi_session_state.json"
RECONCILE_TRIGGER_FILE = VAR_DIR / "reconcile.trigger"
SESSION_LOG_DIR = LOGS_DIR / "sessions"
STOP_JOIN_TIMEOUT_SEC = 30.0

_runner_settings = get_section("runner")
_log_rotation = get_section("log_rotation")

RECONCILE_INTERVAL_SEC = float(_runner_settings.get("reconcile_interval_sec", 5))
STATUS_INTERVAL_SEC = float(_runner_settings.get("status_interval_sec", 15))
HEARTBEAT_INTERVAL_SEC = float(_runner_settings.get("heartbeat_interval_sec", 10))
MAX_RESTART_ATTEMPTS = int(_runner_settings.get("max_restart_attempts", 3))
_MAX_CONCURRENT_RESTARTS = int(_runner_settings.get("max_concurrent_restarts", 3))
_RESTART_BACKOFF = list(_runner_settings.get("restart_backoff_sec") or [5, 15, 45])
_WATCHDOG_INTERVAL_SEC = float(_runner_settings.get("watchdog_interval_sec", 30))
_ERROR_HISTORY_SIZE = int(_runner_settings.get("error_history_size", 5))

_log_levels = get_section("logging")
LOG_MAX_BYTES = int(_log_rotation.get("max_bytes", 5_242_880))
LOG_BACKUP_COUNT = int(_log_rotation.get("backup_count", 5))
_MANAGER_LOG_LEVEL = getattr(logging, str(_log_levels.get("manager_level", "INFO")).upper(), logging.INFO)
_BOT_LOG_LEVEL = getattr(logging, str(_log_levels.get("bot_level", "INFO")).upper(), logging.INFO)


class WorkerState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class _RestartMeta:
    attempts: int = 0
    next_restart_at: float = 0.0
    last_error: str | None = None


@dataclass
class _AccountWorker:
    username: str
    thread: threading.Thread
    stop_event: threading.Event = field(default_factory=threading.Event)
    state: WorkerState = WorkerState.STARTING
    miner: Any = None
    started_at: int = 0
    last_heartbeat: int = 0
    last_error: str | None = None


def read_desired_sessions() -> dict[str, dict]:
    """Desired bots from var/sessions.json (atomic read)."""
    return read_sessions_file()


def notify_sessions_changed() -> None:
    """Signal multi_session_runner to reconcile immediately (API / file watcher)."""
    ensure_dirs()
    RECONCILE_TRIGGER_FILE.write_text(str(int(time.time())), encoding="utf-8")


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
            level=_MANAGER_LOG_LEVEL,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    root.setLevel(_MANAGER_LOG_LEVEL)
    manager_log = LOGS_DIR / "multi_session_runner.log"
    if not any(
        getattr(h, "baseFilename", None) == str(manager_log) for h in root.handlers
    ):
        fh = logging.handlers.RotatingFileHandler(
            manager_log,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
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
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        bot.addHandler(fh)
        bot.setLevel(_BOT_LOG_LEVEL)
        bot.propagate = True
    return bot


class _RunnerWatchdog(threading.Thread):
    """Force reconcile if loop stalls; log runner health."""

    def __init__(self, manager: "MultiSessionManager") -> None:
        super().__init__(daemon=True, name="runner-watchdog")
        self._manager = manager
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        stale_threshold = RECONCILE_INTERVAL_SEC * 3
        while not self._stop.is_set() and not self._manager._shutdown.is_set():
            self._stop.wait(_WATCHDOG_INTERVAL_SEC)
            if self._manager._shutdown.is_set():
                break
            last = self._manager._last_reconcile_at
            if last and time.time() - last > stale_threshold:
                logger.warning(
                    "Watchdog: reconcile stale (%.0fs) — forcing",
                    time.time() - last,
                )
                self._manager._reconcile_now.set()


class _SessionsFileWatcher(threading.Thread):
    """Poll sessions.json mtime and trigger immediate reconcile."""

    def __init__(self, on_change: Callable[[], None]) -> None:
        super().__init__(daemon=True, name="sessions-watcher")
        self._on_change = on_change
        self._stop = threading.Event()
        self._last_mtime = 0.0

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                if RECONCILE_TRIGGER_FILE.exists():
                    self._on_change()
                    try:
                        RECONCILE_TRIGGER_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
                if SESSIONS_FILE.exists():
                    mtime = SESSIONS_FILE.stat().st_mtime
                    if mtime != self._last_mtime:
                        self._last_mtime = mtime
                        self._on_change()
            except Exception as e:
                logger.debug("sessions watcher: %s", e)
            self._stop.wait(0.5)


class MultiSessionManager:
    def __init__(self) -> None:
        self._workers: dict[str, _AccountWorker] = {}
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        self._reconcile_now = threading.Event()
        self._streamers: list = []
        self._reconcile_errors: dict[str, str] = {}
        self._restart_meta: dict[str, _RestartMeta] = {}
        self._error_history: dict[str, list[dict]] = {}
        self._watcher: _SessionsFileWatcher | None = None
        self._watchdog: _RunnerWatchdog | None = None
        self._last_reconcile_at: float = 0.0
        self._restart_sem = threading.Semaphore(_MAX_CONCURRENT_RESTARTS)

    def _account_ready(self, username: str) -> str | None:
        if not get_account_config(username):
            return "missing_json_config"
        if not (COOKIES_DIR / f"{username}.pkl").exists():
            return "missing_cookie"
        return None

    def _backoff_delay(self, attempt: int) -> float:
        idx = min(max(attempt - 1, 0), len(_RESTART_BACKOFF) - 1)
        return float(_RESTART_BACKOFF[idx])

    def _append_error_history(self, username: str, error: str, source: str = "worker") -> None:
        entry = {"ts": int(time.time()), "error": error, "source": source}
        with self._lock:
            hist = self._error_history.setdefault(username, [])
            hist.append(entry)
            if len(hist) > _ERROR_HISTORY_SIZE:
                del hist[: -_ERROR_HISTORY_SIZE]

    def _record_worker_failure(self, username: str, error: str | None) -> None:
        err = error or "unknown_error"
        self._append_error_history(username, err)
        meta = self._restart_meta.setdefault(username, _RestartMeta())
        meta.attempts += 1
        meta.last_error = error
        if meta.attempts < MAX_RESTART_ATTEMPTS:
            meta.next_restart_at = time.time() + self._backoff_delay(meta.attempts)
        else:
            meta.next_restart_at = 0.0
            if meta.attempts >= MAX_RESTART_ATTEMPTS:
                self._reconcile_errors[username] = err

    def _clear_restart_meta(self, username: str) -> None:
        self._restart_meta.pop(username, None)
        self._reconcile_errors.pop(username, None)

    def _can_start_after_failure(self, username: str) -> bool:
        meta = self._restart_meta.get(username)
        if not meta:
            return True
        if meta.attempts >= MAX_RESTART_ATTEMPTS:
            return False
        return time.time() >= meta.next_restart_at

    def _touch_heartbeat(self, username: str) -> None:
        now = int(time.time())
        with self._lock:
            w = self._workers.get(username)
            if w:
                w.last_heartbeat = now

    def _publish_state(self) -> None:
        now = int(time.time())
        with self._lock:
            workers = {}
            for u, w in self._workers.items():
                uptime = now - w.started_at if w.started_at else 0
                stale = (
                    w.state == WorkerState.RUNNING
                    and w.last_heartbeat
                    and now - w.last_heartbeat > HEARTBEAT_INTERVAL_SEC * 3
                )
                workers[u] = {
                    "state": w.state.value,
                    "thread_alive": w.thread.is_alive(),
                    "started_at": w.started_at,
                    "last_heartbeat": w.last_heartbeat,
                    "uptime_sec": uptime,
                    "stale": stale,
                    "last_error": w.last_error,
                }
            errors = dict(self._reconcile_errors)
            restart_meta = {
                u: {
                    "attempts": m.attempts,
                    "next_restart_at": int(m.next_restart_at),
                    "last_error": m.last_error,
                }
                for u, m in self._restart_meta.items()
            }
            error_history = {u: list(h) for u, h in self._error_history.items()}
        desired = read_desired_sessions()
        try:
            import psutil

            proc = psutil.Process(os.getpid())
            mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
            cpu_pct = proc.cpu_percent(interval=None)
        except Exception:
            mem_mb = None
            cpu_pct = None

        payload = {
            "manager_pid": os.getpid(),
            "manager_alive": True,
            "updated_at": now,
            "desired": list(desired.keys()),
            "desired_count": len(desired),
            "running_count": sum(
                1 for w in workers.values() if w.get("thread_alive")
            ),
            "workers": workers,
            "reconcile_errors": errors,
            "restart_meta": restart_meta,
            "error_history": error_history,
            "last_reconcile_at": int(self._last_reconcile_at),
            "manager_memory_mb": mem_mb,
            "manager_cpu_percent": cpu_pct,
        }
        ensure_dirs()
        STATE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _safe_miner_loop(self, username: str, stop: threading.Event) -> None:
        try:
            self._miner_loop(username, stop)
        except Exception as e:
            logger.exception("uncaught miner thread %s: %s", username, e)
            bot_log = _bot_logger(username)
            bot_log.exception("fatal thread error: %s", e)
            with self._lock:
                w = self._workers.get(username)
                if w:
                    w.last_error = str(e)
                    w.state = WorkerState.ERROR
            self._record_worker_failure(username, str(e))
            self._publish_state()

    def _miner_loop(self, username: str, stop: threading.Event) -> None:
        bot_log = _bot_logger(username)
        with self._lock:
            worker = self._workers.get(username)
            if worker:
                worker.state = WorkerState.STARTING
        self._publish_state()

        miner = None
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
                    w.last_heartbeat = int(time.time())
            self._clear_restart_meta(username)
            self._publish_state()

            streamers = self._streamers or streamers_for_miner()
            if not streamers:
                raise RuntimeError("config/streamers.json пуст")

            bot_log.info("miner start")
            log_event("info", "session", f"Майнер {username} стартует", account=username)

            status_stop = threading.Event()

            def heartbeat_loop() -> None:
                while not status_stop.is_set() and not stop.is_set():
                    self._touch_heartbeat(username)
                    status_stop.wait(HEARTBEAT_INTERVAL_SEC)

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
                            if miner:
                                miner.end(0, 0)
                        except Exception:
                            if miner:
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
                target=heartbeat_loop, name=f"heartbeat-{username}", daemon=True
            ).start()
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
            self._record_worker_failure(username, str(e))
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
        if not self._can_start_after_failure(username):
            meta = self._restart_meta.get(username)
            if meta and meta.last_error:
                self._reconcile_errors[username] = meta.last_error
            return "restart_backoff_or_max_retries"

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
                target=self._safe_miner_loop,
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
                last_heartbeat=int(time.time()),
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
        if graceful and w.miner:
            try:
                w.miner.end(0, 0)
            except Exception:
                pass
        if graceful:
            w.thread.join(timeout=STOP_JOIN_TIMEOUT_SEC)
        invalidate_twitch(username)
        with self._lock:
            if not w.thread.is_alive():
                self._workers.pop(username, None)
        self._clear_restart_meta(username)
        self._publish_state()
        log_event("warning", "session", f"Поток {username} остановлен", account=username)

    def _prune_dead_workers(self) -> None:
        with self._lock:
            dead = [u for u, w in self._workers.items() if not w.thread.is_alive()]
            for u in dead:
                w = self._workers.pop(u)
                if w.state not in (WorkerState.ERROR, WorkerState.STOPPED):
                    w.state = WorkerState.STOPPED
                if w.state == WorkerState.ERROR and w.last_error:
                    self._record_worker_failure(u, w.last_error)

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
            with self._restart_sem:
                err = self.start_account(username)
            if err:
                actions[username] = f"start_failed:{err}"
                self._append_error_history(username, err, source="reconcile")
            else:
                actions[username] = "started"

        for username in sorted(running - desired_names):
            self.stop_account(username)
            actions[username] = "stopped"
            self._clear_restart_meta(username)

        self._publish_state()
        return actions

    def shutdown_all(self) -> None:
        log_event("info", "session", "Graceful shutdown всех ботов")
        with self._lock:
            names = list(self._workers.keys())
        for name in names:
            self.stop_account(name)
        try:
            from TwitchChannelPointsMiner.platform.chat_hub import shutdown_chat_hub
            from TwitchChannelPointsMiner.platform.gql_queries import shutdown_gql_clients

            shutdown_chat_hub()
            shutdown_gql_clients()
        except Exception as e:
            logger.debug("auxiliary shutdown: %s", e)
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
            self._reconcile_now.set()

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGABRT):
            try:
                signal.signal(sig, handle_signal)
            except (ValueError, OSError, AttributeError):
                pass

        self._watcher = _SessionsFileWatcher(on_change=self._reconcile_now.set)
        self._watcher.start()
        self._watchdog = _RunnerWatchdog(self)
        self._watchdog.start()

        log_event("info", "session", "Multi-session runner запущен (reconcile loop)")
        logger.info(
            "Reconcile every %ss — desired state: %s",
            RECONCILE_INTERVAL_SEC,
            SESSIONS_FILE,
        )
        try:
            while not self._shutdown.is_set():
                self._reconcile_now.wait(timeout=RECONCILE_INTERVAL_SEC)
                self._reconcile_now.clear()
                if self._shutdown.is_set():
                    break
                desired = read_desired_sessions()
                actions = self.reconcile(desired)
                self._last_reconcile_at = time.time()
                if actions:
                    logger.info("reconcile: %s", actions)
        finally:
            if self._watchdog:
                self._watchdog.stop()
            if self._watcher:
                self._watcher.stop()
            self.shutdown_all()
            _clear_manager_pid()
            self._publish_state()
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
                    "last_heartbeat": w.last_heartbeat,
                    "last_error": w.last_error,
                }
                for u, w in self._workers.items()
            }
        desired = read_desired_sessions()
        with self._lock:
            error_history = {u: list(h) for u, h in self._error_history.items()}
        return {
            "manager_pid": manager_pid_running() or os.getpid(),
            "desired": desired,
            "workers": workers,
            "reconcile_errors": dict(self._reconcile_errors),
            "restart_meta": {
                u: {"attempts": m.attempts, "next_restart_at": m.next_restart_at}
                for u, m in self._restart_meta.items()
            },
            "error_history": error_history,
            "last_reconcile_at": int(self._last_reconcile_at),
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


def worker_resource_stats(username: str, runtime: dict) -> dict:
    """Per-bot stats for /api/sessions/debug (shared process — manager RSS split estimate)."""
    workers = runtime.get("workers") or {}
    meta = workers.get(username) or {}
    now = int(time.time())
    started = int(meta.get("started_at") or 0)
    uptime = now - started if started else 0
    mgr_mem = runtime.get("manager_memory_mb")
    running = int(runtime.get("running_count") or 1) or 1
    est_mem = round(mgr_mem / running, 1) if mgr_mem else None
    restart = (runtime.get("restart_meta") or {}).get(username) or {}
    errors = (runtime.get("error_history") or {}).get(username) or []
    return {
        "uptime_sec": uptime,
        "last_error": meta.get("last_error"),
        "last_heartbeat": meta.get("last_heartbeat"),
        "stale": meta.get("stale"),
        "state": meta.get("state"),
        "thread_alive": meta.get("thread_alive"),
        "memory_mb_est": est_mem,
        "restart_attempts": restart.get("attempts"),
        "next_restart_at": restart.get("next_restart_at"),
        "error_history": errors[-5:],
    }
