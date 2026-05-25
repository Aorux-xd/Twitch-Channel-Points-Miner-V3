import json

from TwitchChannelPointsMiner.platform.accounts import list_account_usernames
from TwitchChannelPointsMiner.platform.paths import COOKIES_DIR, STATUS_DIR
from TwitchChannelPointsMiner.platform.sessions import load_sessions
from TwitchChannelPointsMiner.platform.streamers_store import _base_entries
from TwitchChannelPointsMiner.platform.twitch_gql import POINTS_CACHE_FILE, get_points_snapshot


def _accounts_with_cookies(running_first: bool = True) -> list[str]:
    sessions = load_sessions()
    running = list(sessions.keys())
    all_acc = [
        u
        for u in list_account_usernames()
        if (COOKIES_DIR / f"{u}.pkl").exists()
    ]
    if not all_acc:
        all_acc = list_account_usernames()
    if running_first:
        return running + [a for a in all_acc if a not in running]
    return all_acc


def _dashboard_from_cache(accounts: list[str], sessions: dict) -> dict | None:
    if not POINTS_CACHE_FILE.exists():
        return None
    try:
        cached = json.loads(POINTS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    acc_snap = cached.get("accounts") or {}
    per_account = []
    for username in accounts:
        row = acc_snap.get(username) or {}
        per_account.append(
            {
                "username": username,
                "points": int(sum(row.values())),
                "streamers_online": 0,
                "by_streamer": row,
            }
        )
    return {
        "total_points": int(cached.get("total_points", 0)),
        "active_sessions": len(sessions),
        "online_streamers": 0,
        "accounts": per_account,
        "per_streamer": cached.get("per_streamer", {}),
        "from_cache": True,
    }


def dashboard_stats(force: bool = False) -> dict:
    streamers = [s["login"] for s in _base_entries()]
    accounts = _accounts_with_cookies()
    sessions = load_sessions()

    if not accounts:
        return {
            "total_points": 0,
            "active_sessions": len(sessions),
            "online_streamers": 0,
            "accounts": [],
            "per_streamer": {},
        }

    if not streamers:
        cached_view = _dashboard_from_cache(accounts, sessions)
        if cached_view:
            return cached_view
        return {
            "total_points": 0,
            "active_sessions": len(sessions),
            "online_streamers": 0,
            "accounts": [
                {"username": u, "points": 0, "streamers_online": 0, "by_streamer": {}}
                for u in accounts
            ],
            "per_streamer": {},
        }

    snap = get_points_snapshot(streamers, accounts, force=force)
    per_account = []
    for username in accounts:
        row = snap.get("accounts", {}).get(username, {})
        per_account.append(
            {
                "username": username,
                "points": sum(row.values()),
                "streamers_online": 0,
                "by_streamer": row,
            }
        )

    from TwitchChannelPointsMiner.platform.streamers_store import list_streamers

    online = sum(1 for s in list_streamers(enrich=True) if s.get("is_live"))

    return {
        "total_points": int(snap.get("total_points", 0)),
        "active_sessions": len(sessions),
        "online_streamers": online,
        "accounts": per_account,
        "per_streamer": snap.get("per_streamer", {}),
    }


def active_streams() -> list[dict]:
    """Live channels where running bots report is_online (session status), not points cache."""
    from TwitchChannelPointsMiner.platform.streamers_store import list_streamers

    sessions = load_sessions()
    if not sessions:
        return []

    meta_by_login = {s["login"]: s for s in list_streamers(enrich=True)}
    live_meta = {k: v for k, v in meta_by_login.items() if v.get("is_live")}

    by_channel: dict[str, dict] = {}

    for username in sessions:
        path = STATUS_DIR / f"{username}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for st in data.get("streamers") or []:
            login = str(st.get("login") or "").lower()
            if not login or not st.get("is_online"):
                continue
            if login not in live_meta:
                continue
            row = by_channel.setdefault(
                login,
                {"accounts": set(), "channel_points": 0},
            )
            row["accounts"].add(username)
            row["channel_points"] += int(st.get("channel_points") or 0)

    out = []
    for login, row in by_channel.items():
        meta = live_meta.get(login, {})
        accounts = sorted(row["accounts"])
        if not accounts:
            continue
        out.append(
            {
                "login": login,
                "display_name": meta.get("display_name", login),
                "avatar_url": meta.get("avatar_url", ""),
                "channel_points": row["channel_points"],
                "accounts": accounts,
            }
        )
    return sorted(out, key=lambda x: -x["channel_points"])
