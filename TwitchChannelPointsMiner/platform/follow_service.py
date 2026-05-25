"""Follow a Twitch channel for panel bot accounts (GQL + integrity)."""

from __future__ import annotations

import logging

import requests

from TwitchChannelPointsMiner.constants import BROWSER_CLIENT_ID, GQLOperations
from TwitchChannelPointsMiner.platform.accounts import accounts_with_cookies
from TwitchChannelPointsMiner.platform.twitch_gql import _channel_id, get_twitch

logger = logging.getLogger(__name__)

_FOLLOW_MUTATION = """
mutation FollowButton_FollowUser($input: FollowUserInput!) {
  followUser(input: $input) {
    follow {
      user { id login displayName }
    }
    error { code }
  }
}
"""


def _gql_headers(client) -> dict[str, str]:
    token = client.twitch_login.get_auth_token()
    return {
        "Authorization": f"OAuth {token}",
        "Client-Id": BROWSER_CLIENT_ID,
        "Client-Session-Id": client.client_session,
        "Client-Version": client.client_version,
        "User-Agent": client.user_agent,
        "X-Device-Id": client.device_id,
        "Origin": "https://www.twitch.tv",
        "Referer": "https://www.twitch.tv/",
    }


def _fetch_integrity(client) -> str | None:
    try:
        resp = requests.post(
            GQLOperations.integrity_url,
            json={},
            headers=_gql_headers(client),
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
    except requests.RequestException as e:
        logger.debug("integrity fetch: %s", e)
    return None


def is_following(account: str, channel_login: str) -> bool:
    channel_login = channel_login.strip().lower()
    client = get_twitch(account)
    if not client:
        return False
    try:
        follows = client.get_followers(limit=100)
        if channel_login in follows:
            return True
        # paginate a bit more if needed
        follows = client.get_followers(limit=500)
        return channel_login in follows
    except Exception:
        return False


def follow_channel(account: str, channel_login: str) -> dict:
    channel_login = channel_login.strip().lower()
    client = get_twitch(account)
    if not client:
        return {
            "account": account,
            "ok": False,
            "skipped": False,
            "error": "нет cookie / login",
        }

    if is_following(account, channel_login):
        return {"account": account, "ok": True, "skipped": True, "error": None}

    broadcaster_id = _channel_id(client, channel_login)
    if not broadcaster_id:
        return {
            "account": account,
            "ok": False,
            "skipped": False,
            "error": "канал не найден",
        }

    headers = _gql_headers(client)
    integrity = _fetch_integrity(client)
    if integrity:
        headers["Client-Integrity"] = integrity

    body = {
        "operationName": "FollowButton_FollowUser",
        "query": _FOLLOW_MUTATION,
        "variables": {
            "input": {
                "targetID": broadcaster_id,
                "disableNotifications": False,
            }
        },
    }

    try:
        resp = requests.post(
            GQLOperations.url, json=body, headers=headers, timeout=20
        )
        payload = resp.json()
    except requests.RequestException as e:
        return {
            "account": account,
            "ok": False,
            "skipped": False,
            "error": str(e),
        }

    if payload.get("errors"):
        msg = payload["errors"][0].get("message", "GQL error")
        if "integrity" in msg.lower():
            return {
                "account": account,
                "ok": False,
                "skipped": False,
                "error": (
                    "Twitch блокирует авто-подписку с сервера (integrity). "
                    f"Подпишитесь вручную: https://www.twitch.tv/{channel_login}"
                ),
                "code": "INTEGRITY",
            }
        return {
            "account": account,
            "ok": False,
            "skipped": False,
            "error": msg,
        }

    data = (payload.get("data") or {}).get("followUser") or {}
    err = data.get("error")
    if err:
        code = err.get("code") if isinstance(err, dict) else str(err)
        return {
            "account": account,
            "ok": False,
            "skipped": False,
            "error": f"followUser error: {code}",
        }

    if data.get("follow"):
        return {"account": account, "ok": True, "skipped": False, "error": None}

    if is_following(account, channel_login):
        return {"account": account, "ok": True, "skipped": False, "error": None}

    return {
        "account": account,
        "ok": False,
        "skipped": False,
        "error": "неизвестный ответ Twitch",
    }


def follow_accounts(channel_login: str, session: str | None = None) -> dict:
    channel_login = channel_login.strip().lower()
    if not channel_login:
        return {"ok": False, "error": "login стримера обязателен", "results": []}

    accounts = accounts_with_cookies(session)
    if not accounts:
        return {"ok": False, "error": "нет аккаунтов с cookie", "results": []}

    results = [follow_channel(acc, channel_login) for acc in accounts]
    ok_count = sum(1 for r in results if r.get("ok") and not r.get("skipped"))
    skipped = sum(1 for r in results if r.get("skipped"))
    return {
        "ok": any(r.get("ok") for r in results),
        "ok_count": ok_count,
        "skipped": skipped,
        "total": len(results),
        "results": results,
    }
