import json
import threading
from typing import Any

from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.paths import STREAMERS_FILE, ensure_dirs
from TwitchChannelPointsMiner.platform.twitch_gql import (
    get_cached_streamers_meta,
    refresh_streamers_meta_cache,
)

_refresh_lock = threading.Lock()


def _read() -> dict:
    ensure_dirs()
    if not STREAMERS_FILE.exists():
        return {"streamers": []}
    try:
        return json.loads(STREAMERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"streamers": []}


def _write(data: dict):
    ensure_dirs()
    STREAMERS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _normalize_entry(raw: Any) -> dict | None:
    if isinstance(raw, str):
        login = raw.strip()
        if not login:
            return None
        return {
            "login": login.lower(),
            "claim_drops": True,
            "high_priority": False,
        }
    if isinstance(raw, dict):
        login = str(raw.get("login", "")).strip().lower()
        if not login:
            return None
        return {
            "login": login,
            "claim_drops": bool(raw.get("claim_drops", True)),
            "high_priority": bool(raw.get("high_priority", False)),
        }
    return None


def _base_entries() -> list[dict]:
    data = _read()
    entries = []
    for raw in data.get("streamers", []):
        entry = _normalize_entry(raw)
        if entry:
            entries.append(entry)
    entries.sort(key=lambda x: (not x["high_priority"], x["login"]))
    return entries


def list_streamers(enrich: bool = True) -> list[dict]:
    entries = _base_entries()
    if not entries:
        return []
    if enrich:
        return get_cached_streamers_meta(entries)
    return entries


def refresh_all_meta_background(account: str | None = None):
    def _job():
        try:
            with _refresh_lock:
                entries = _base_entries()
                if entries:
                    refresh_streamers_meta_cache(entries, account=account)
        except Exception:
            pass

    threading.Thread(target=_job, daemon=True).start()


def add_streamer(login: str, claim_drops: bool, high_priority: bool) -> dict:
    login = login.strip().lower()
    if not login:
        raise ValueError("login is required")

    data = _read()
    streamers = []
    found = False
    for raw in data.get("streamers", []):
        entry = _normalize_entry(raw)
        if not entry:
            continue
        if entry["login"] == login:
            entry["claim_drops"] = claim_drops
            entry["high_priority"] = high_priority
            found = True
        streamers.append(entry)
    if not found:
        streamers.append(
            {
                "login": login,
                "claim_drops": claim_drops,
                "high_priority": high_priority,
            }
        )

    _write({"streamers": streamers})
    log_event(
        "info",
        "streamer",
        f"Добавлен стример {login} (авто-сбор={claim_drops}, приоритет={high_priority})",
        streamer=login,
    )

    entry = next(s for s in streamers if s["login"] == login)

    def _enrich_one():
        with _refresh_lock:
            enriched = refresh_streamers_meta_cache([entry])
            return enriched[0] if enriched else entry

    threading.Thread(target=_enrich_one, daemon=True).start()
    return get_cached_streamers_meta([entry])[0]


def remove_streamer(login: str):
    login = login.strip().lower()
    data = _read()
    streamers = []
    for raw in data.get("streamers", []):
        entry = _normalize_entry(raw)
        if entry and entry["login"] != login:
            streamers.append(entry)
    _write({"streamers": streamers})
    log_event("info", "streamer", f"Удалён стример {login}", streamer=login)


def streamers_for_miner():
    from TwitchChannelPointsMiner.classes.entities.Streamer import (
        Streamer,
        StreamerSettings,
    )

    result = []
    for s in _base_entries():
        settings = StreamerSettings(
            claim_drops=s["claim_drops"],
            watch_streak=True,
            make_predictions=True,
            follow_raid=True,
        )
        result.append(Streamer(s["login"], settings=settings))
    return result
