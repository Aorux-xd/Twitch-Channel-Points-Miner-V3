"""Authenticated Twitch GQL helpers (uses bot cookies)."""

import copy
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

from TwitchChannelPointsMiner.classes.Twitch import Twitch
from TwitchChannelPointsMiner.constants import (
    BROWSER_CLIENT_ID,
    CLIENT_ID,
    GQLOperations,
)
from TwitchChannelPointsMiner.utils import get_user_agent

from TwitchChannelPointsMiner.platform.network_util import twitch_network_ok
from TwitchChannelPointsMiner.platform.paths import COOKIES_DIR, VAR_DIR, ensure_dirs

logger = logging.getLogger(__name__)

META_CACHE_FILE = VAR_DIR / "streamers_meta.json"
POINTS_CACHE_FILE = VAR_DIR / "points_cache.json"
META_TTL = 45
POINTS_TTL = 30
# When Twitch is unreachable, still serve last known cache (up to 7 days).
OFFLINE_CACHE_TTL = 86400 * 7

_twitch_clients: dict[str, Twitch] = {}
_id_cache: dict[str, str] = {}


def invalidate_twitch(username: str | None = None) -> None:
    """Drop cached Twitch client(s) after cookie delete or re-auth."""
    if username:
        _twitch_clients.pop(username.strip(), None)
    else:
        _twitch_clients.clear()


def _pick_account(preferred: str | None = None) -> str | None:
    if preferred:
        if (COOKIES_DIR / f"{preferred}.pkl").exists():
            return preferred
    for p in sorted(COOKIES_DIR.glob("*.pkl")):
        return p.stem
    return None


def get_twitch(username: str | None = None) -> Twitch | None:
    if not twitch_network_ok():
        return None
    account = _pick_account(username)
    if not account:
        return None
    if account in _twitch_clients:
        return _twitch_clients[account]
    try:
        client = Twitch(account, get_user_agent("CHROME"))
        client.login()
        _twitch_clients[account] = client
        return client
    except Exception as e:
        logger.warning("Twitch login failed for %s: %s", account, e)
        return None


def _channel_id(client: Twitch, login: str) -> str | None:
    key = login.lower()
    if key in _id_cache:
        return _id_cache[key]
    try:
        cid = client.get_channel_id(login)
        _id_cache[key] = cid
        return cid
    except Exception:
        return None


def _is_live(client: Twitch, login: str) -> bool:
    cid = _channel_id(client, login)
    if not cid:
        return False
    try:
        payload = copy.deepcopy(GQLOperations.WithIsStreamLiveQuery)
        payload["variables"] = {"id": cid}
        resp = client.post_gql_request(payload)
        stream = resp.get("data", {}).get("user", {}).get("stream")
        return stream is not None
    except Exception:
        return False


def _avatars_helix(client: Twitch, logins: list[str]) -> dict[str, str]:
    token = client.twitch_login.get_auth_token()
    if not token:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(logins), 100):
        chunk = logins[i : i + 100]
        params = [("login", x) for x in chunk]
        try:
            resp = requests.get(
                "https://api.twitch.tv/helix/users",
                params=params,
                headers={
                    "Client-ID": CLIENT_ID,
                    "Authorization": f"Bearer {token}",
                },
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            for item in resp.json().get("data", []):
                out[item.get("login", "").lower()] = item.get("profile_image_url", "")
        except requests.RequestException:
            pass
    return out


def enrich_streamer_meta(entries: list[dict], account: str | None = None) -> list[dict]:
    if not twitch_network_ok():
        return get_cached_streamers_meta(entries) if entries else []
    client = get_twitch(account)
    if not client or not entries:
        return [
            {
                **e,
                "display_name": e["login"],
                "avatar_url": "",
                "is_live": False,
            }
            for e in entries
        ]

    logins = [e["login"] for e in entries]
    avatars = _avatars_helix(client, logins)
    live_map: dict[str, bool] = {}

    with ThreadPoolExecutor(max_workers=min(8, len(entries))) as pool:
        futures = {pool.submit(_is_live, client, e["login"]): e["login"] for e in entries}
        try:
            for fut in as_completed(futures, timeout=20):
                login = futures[fut]
                try:
                    live_map[login] = fut.result()
                except Exception:
                    live_map[login] = False
        except TimeoutError:
            for login in futures.values():
                live_map.setdefault(login, False)

    out = []
    for e in entries:
        login = e["login"]
        out.append(
            {
                **e,
                "display_name": login,
                "avatar_url": avatars.get(login, ""),
                "is_live": live_map.get(login, False),
            }
        )
    return out


def _read_cache(path: Path, ttl: int) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if __import__("time").time() - float(data.get("ts", 0)) <= ttl:
            return data
    except Exception:
        pass
    return None


def _read_cache_offline(path: Path) -> dict | None:
    """Last cached payload when live Twitch API is unavailable."""
    return _read_cache(path, OFFLINE_CACHE_TTL)


def _write_cache(path: Path, payload: dict):
    ensure_dirs()
    payload["ts"] = __import__("time").time()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cached_streamers_meta(entries: list[dict]) -> list[dict]:
    ttl = META_TTL if twitch_network_ok() else OFFLINE_CACHE_TTL
    cached = _read_cache(META_CACHE_FILE, ttl)
    meta_by_login = {}
    if cached:
        for row in cached.get("streamers", []):
            meta_by_login[row.get("login", "").lower()] = row

    out = []
    for e in entries:
        m = meta_by_login.get(e["login"], {})
        out.append(
            {
                **e,
                "display_name": m.get("display_name", e["login"]),
                "avatar_url": m.get("avatar_url", ""),
                "is_live": m.get("is_live", False),
            }
        )
    return out


def refresh_streamers_meta_cache(entries: list[dict], account: str | None = None):
    if not twitch_network_ok():
        return get_cached_streamers_meta(entries)
    try:
        enriched = enrich_streamer_meta(entries, account=account)
        _write_cache(META_CACHE_FILE, {"streamers": enriched})
        return enriched
    except Exception as e:
        logger.warning("refresh_streamers_meta_cache failed: %s", e)
        return get_cached_streamers_meta(entries)


def fetch_channel_points(
    streamer_login: str, account: str | None = None
) -> int | None:
    client = get_twitch(account)
    if not client:
        return None
    try:
        payload = copy.deepcopy(GQLOperations.ChannelPointsContext)
        payload["variables"] = {"channelLogin": streamer_login.lower()}
        resp = client.post_gql_request(payload)
        channel = resp.get("data", {}).get("community", {}).get("channel", {})
        return int(channel.get("self", {}).get("communityPoints", {}).get("balance", 0))
    except Exception:
        return None


def _gql_browser_post(client: Twitch, body: dict) -> dict:
    token = client.twitch_login.get_auth_token()
    if not token:
        return {}
    headers = {
        "Authorization": f"OAuth {token}",
        "Client-Id": BROWSER_CLIENT_ID,
        "Client-Session-Id": client.client_session,
        "Client-Version": client.client_version,
        "User-Agent": client.user_agent,
        "X-Device-Id": client.device_id,
    }
    try:
        response = requests.post(
            GQLOperations.url, json=body, headers=headers, timeout=20
        )
        return response.json()
    except requests.RequestException as e:
        logger.warning("browser GQL failed: %s", e)
        return {}


def _normalize_reward_row(r: dict) -> dict | None:
    rid = r.get("id")
    if not rid:
        return None
    title = (r.get("title") or "").strip()
    prompt = (r.get("prompt") or "").strip()
    name = title or prompt or "Награда"
    img = r.get("image") or r.get("defaultImage") or {}
    image_url = img.get("url") if isinstance(img, dict) else None
    return {
        "id": str(rid),
        "name": name,
        "title": title or name,
        "prompt": prompt or None,
        "cost": int(r.get("cost") or 0),
        "requiresText": bool(
            r.get("isUserInputRequired") or r.get("userInputRequired")
        ),
        "inStock": bool(r.get("isInStock", True)),
        "isEnabled": bool(r.get("isEnabled", True)),
        "imageUrl": image_url,
    }


def _collect_rewards_from_channel(channel: dict) -> list[dict]:
    merged: dict[str, dict] = {}
    settings = channel.get("communityPointsSettings") or {}
    for r in settings.get("customRewards") or []:
        row = _normalize_reward_row(r)
        if row:
            merged[row["id"]] = row
    return list(merged.values())


def fetch_channel_rewards(
    streamer_login: str, account: str | None = None
) -> list[dict]:
    client = get_twitch(account)
    if not client:
        return []
    login = streamer_login.lower()
    try:
        body = {
            "operationName": "ChannelPointsCustomRewardsList",
            "query": GQLOperations.ChannelPointsCustomRewardsListQuery,
            "variables": {"login": login},
        }
        resp = _gql_browser_post(client, body)
        if resp.get("errors"):
            logger.warning(
                "ChannelPointsCustomRewardsList: %s",
                resp["errors"][0].get("message"),
            )
        channel = (resp.get("data") or {}).get("channel") or {}
        out = _collect_rewards_from_channel(channel)
        if out:
            return sorted(
                out,
                key=lambda x: (
                    0 if x.get("isEnabled", True) else 1,
                    x.get("cost") or 0,
                    x.get("name") or "",
                ),
            )

        payload = copy.deepcopy(GQLOperations.ChannelPointsContext)
        payload["variables"] = {"channelLogin": login}
        resp = client.post_gql_request(payload)
        channel = (resp.get("data") or {}).get("community", {}).get("channel") or {}
        return sorted(
            _collect_rewards_from_channel(channel),
            key=lambda x: (x.get("cost") or 0, x.get("name") or ""),
        )
    except Exception as e:
        logger.warning("fetch_channel_rewards failed: %s", e)
        return []


def _reward_by_id(
    streamer_login: str, reward_id: str, account: str | None = None
) -> dict | None:
    for row in fetch_channel_rewards(streamer_login, account=account):
        if str(row.get("id")) == str(reward_id):
            return row
    return None


def redeem_channel_reward(
    streamer_login: str,
    reward_id: str,
    account: str,
    *,
    text_input: str | None = None,
    reward_meta: dict | None = None,
) -> dict[str, Any]:
    """
    Redeem a channel custom reward via GQL RedeemCommunityPointsCustomReward.
    Uses browser Client-Id + bot OAuth cookie (same as twitch.tv activate flow).
    """
    if not twitch_network_ok():
        return {"ok": False, "error": "Twitch недоступен (сеть/DNS)"}

    client = get_twitch(account)
    if not client:
        return {"ok": False, "error": f"Нет cookie или логин не удался: {account}"}

    channel_id = _channel_id(client, streamer_login)
    if not channel_id:
        return {"ok": False, "error": f"Канал не найден: {streamer_login}"}

    meta = reward_meta or _reward_by_id(streamer_login, reward_id, account=account)
    if not meta:
        return {"ok": False, "error": "Награда не найдена на канале (устаревший id?)"}

    if meta.get("isEnabled") is False:
        return {
            "ok": False,
            "error": "Награда отключена на канале (включите в Twitch Creator Dashboard)",
            "code": "DISABLED",
        }

    title = str(meta.get("title") or meta.get("name") or "")
    cost = int(meta.get("cost") or 0)
    prompt = meta.get("prompt")
    if meta.get("requiresText") and not (text_input or "").strip():
        return {"ok": False, "error": "Награда требует текстовый ввод"}

    gql_input = {
        "channelID": channel_id,
        "cost": cost,
        "prompt": prompt,
        "rewardID": str(reward_id),
        "textInput": (text_input or "").strip() or None,
        "title": title,
        "transactionID": str(uuid.uuid4()),
    }

    token = client.twitch_login.get_auth_token()
    if not token:
        return {"ok": False, "error": "Нет auth-token в cookie"}

    from TwitchChannelPointsMiner.platform.gql_queries import (
        REDEEM_COMMUNITY_POINTS_CUSTOM_REWARD,
        post_browser_gql,
        redeem_mutation_body,
    )

    payload = post_browser_gql(
        client,
        operation_name="RedeemCommunityPointsCustomReward",
        variables=redeem_mutation_body(gql_input),
        query=REDEEM_COMMUNITY_POINTS_CUSTOM_REWARD.strip(),
        use_persisted=True,
        timeout=20,
    )

    if payload.get("errors"):
        err0 = payload["errors"][0]
        msg = err0.get("message", "GQL error")
        code = "PERSISTED_QUERY" if "PersistedQueryNotFound" in msg else "GQL_ERROR"
        return {"ok": False, "error": msg, "code": code}

    data = (payload.get("data") or {}).get("redeemCommunityPointsCustomReward") or {}
    err = data.get("error")
    if err:
        code = err.get("code") or "UNKNOWN"
        detail = err.get("message") or ""
        msg = _redeem_error_message(code)
        if detail and detail not in msg:
            msg = f"{msg} ({detail})"
        return {"ok": False, "error": msg, "code": code}

    redemption = data.get("redemption") or {}
    return {
        "ok": True,
        "redemption_id": redemption.get("id"),
        "status": redemption.get("status"),
        "reward_id": redemption.get("rewardID") or reward_id,
    }


def _redeem_error_message(code: str) -> str:
    messages = {
        "INSUFFICIENT_POINTS": "Недостаточно баллов",
        "NOT_ENOUGH_POINTS": "Недостаточно баллов",
        "OUT_OF_STOCK": "Награда закончилась (out of stock)",
        "UNAVAILABLE": "Награда недоступна",
        "MAX_PER_STREAM": "Лимит на стрим исчерпан",
        "MAX_PER_USER_PER_STREAM": "Лимит на пользователя исчерпан",
        "GLOBAL_COOLDOWN": "Глобальный кулдаун награды",
        "COOLDOWN": "Кулдаун — подождите",
        "INVALID_INPUT": "Неверные данные награды (title/cost/prompt)",
        "REWARD_DISABLED": "Награда отключена",
        "DISABLED": "Награда отключена на канале",
        "SUB_ONLY": "Только для подписчиков",
        "DUPLICATE_TRANSACTION": "Повторная транзакция — попробуйте снова",
        "USER_NOT_SUBSCRIBED": "Нужна подписка на канал",
        "CHANNEL_POINTS_DISABLED": "Баллы канала отключены",
    }
    return messages.get(code, f"Twitch: {code}")


def refresh_points_cache(streamer_logins: list[str], accounts: list[str]) -> dict:
    """Snapshot channel points per account per streamer via GQL."""
    stale = _read_cache_offline(POINTS_CACHE_FILE)
    if not twitch_network_ok():
        return stale or {
            "accounts": {},
            "total_points": 0,
            "per_streamer": {},
        }
    snapshot: dict[str, dict[str, int]] = {acc: {} for acc in accounts}

    def _fetch_pair(account: str, login: str):
        pts = fetch_channel_points(login, account=account)
        return account, login, pts

    pairs = [(acc, login) for acc in accounts for login in streamer_logins]
    workers = min(12, max(1, len(pairs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_pair, acc, login) for acc, login in pairs]
        try:
            for fut in as_completed(futures, timeout=90):
                try:
                    account, login, pts = fut.result()
                    if pts is not None:
                        snapshot.setdefault(account, {})[login] = pts
                except Exception:
                    pass
        except TimeoutError:
            logger.warning("refresh_points_cache timed out, using partial data")
            if stale:
                return stale
    total = sum(sum(v.values()) for v in snapshot.values())
    payload = {
        "accounts": snapshot,
        "total_points": total,
        "per_streamer": {},
    }
    for login in streamer_logins:
        payload["per_streamer"][login] = sum(
            snapshot.get(acc, {}).get(login, 0) for acc in accounts
        )
    _write_cache(POINTS_CACHE_FILE, payload)
    return payload


def get_points_snapshot(
    streamer_logins: list[str], accounts: list[str], force: bool = False
) -> dict:
    empty = {"accounts": {}, "total_points": 0, "per_streamer": {}}
    if not twitch_network_ok():
        return _read_cache_offline(POINTS_CACHE_FILE) or empty

    cached = _read_cache(POINTS_CACHE_FILE, POINTS_TTL)
    stale = _read_cache_offline(POINTS_CACHE_FILE) if not cached else None
    best = cached or stale

    if streamer_logins and accounts and (force or not cached):
        threading.Thread(
            target=refresh_points_cache,
            args=(streamer_logins, accounts),
            daemon=True,
        ).start()

    return best or empty


def drop_twitch_client(username: str):
    _twitch_clients.pop(username, None)
