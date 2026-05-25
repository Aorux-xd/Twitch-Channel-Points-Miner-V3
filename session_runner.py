import argparse
import importlib.util
import json
import signal
import sys
import threading
import time
from pathlib import Path

from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.paths import ROOT, STATUS_DIR, ensure_dirs
from TwitchChannelPointsMiner.platform.miner_streamer_sync import sync_streamers_to_miner
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner

_miner_ref = None


def _load_create_miner(username: str):
    """Prefer JSON config + miner_factory; fall back to legacy accounts/<user>.py."""
    from TwitchChannelPointsMiner.platform.account_store import get_account_config
    from TwitchChannelPointsMiner.platform.miner_factory import create_miner_from_config

    cfg = get_account_config(username)
    if cfg:
        return lambda: create_miner_from_config(username, cfg)

    path = ROOT / "accounts" / f"{username}.py"
    if not path.exists():
        raise FileNotFoundError(
            f"No account config for {username}: add to config/accounts.json or accounts/{username}.py"
        )

    spec = importlib.util.spec_from_file_location(f"account_{username}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load account module: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "create_miner"):
        raise AttributeError(f"{path} must define create_miner()")
    return module.create_miner


def _shutdown(signum, frame):
    global _miner_ref
    username = getattr(_shutdown, "_username", "")
    if _miner_ref is not None:
        try:
            _miner_ref.end(signum, frame)
        except Exception:
            _miner_ref.running = False
            if getattr(_miner_ref, "twitch", None):
                _miner_ref.twitch.running = False
    log_event(
        "warning",
        "session",
        f"Бот {username} получил сигнал остановки и завершает работу",
        account=username or None,
    )
    sys.exit(0)


def _status_loop(miner, username: str, stop: threading.Event):
    ensure_dirs()
    status_path = STATUS_DIR / f"{username}.json"
    stop_flag = STATUS_DIR / f"{username}.stop"
    prev_points: dict[str, int] = {}

    while not stop.is_set():
        try:
            if stop_flag.exists():
                stop_flag.unlink(missing_ok=True)
                log_event(
                    "warning",
                    "session",
                    f"Бот {username} остановлен по запросу панели",
                    account=username,
                )
                try:
                    miner.end(0, 0)
                except Exception:
                    miner.running = False
                    miner.twitch.running = False
                stop.set()
                return

            if getattr(miner, "running", False) and getattr(miner, "streamers", None):
                streamers_payload = []
                for s in miner.streamers:
                    login = s.username
                    pts = int(s.channel_points or 0)
                    streamers_payload.append(
                        {
                            "login": login,
                            "channel_points": pts,
                            "is_online": bool(s.is_online),
                        }
                    )
                    old = prev_points.get(login)
                    if old is not None and pts > old:
                        gained = pts - old
                        log_event(
                            "success",
                            "points",
                            f"{username} заработал {gained} у {login} (всего {pts})",
                            account=username,
                            streamer=login,
                            points=gained,
                        )
                    prev_points[login] = pts

                payload = {
                    "username": username,
                    "updated_at": int(time.time()),
                    "streamers": streamers_payload,
                }
                status_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            try:
                sync_streamers_to_miner(miner, username)
            except Exception:
                pass
        except Exception:
            pass
        stop.wait(15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    args = parser.parse_args()

    username = args.username.strip()
    _shutdown._username = username

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            pass

    global _miner_ref
    try:
        from TwitchChannelPointsMiner.platform.account_store import migrate_py_accounts_to_json

        migrate_py_accounts_to_json()

        create_miner = _load_create_miner(username)
        miner = create_miner()
        _miner_ref = miner
        streamers = streamers_for_miner()
        if not streamers:
            print("No streamers configured in config/streamers.json", file=sys.stderr)
            return 2

        log_event("info", "session", f"Сессия {username} стартует", account=username)

        stop_event = threading.Event()
        threading.Thread(
            target=_status_loop,
            args=(miner, username, stop_event),
            daemon=True,
        ).start()

        miner.mine(streamers, followers=False)
        stop_event.set()
        log_event("warning", "session", f"Сессия {username} завершена", account=username)
        return 0
    except Exception as e:
        log_event("error", "session", f"Сессия {username} ошибка: {e}", account=username)
        print(f"Session failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
