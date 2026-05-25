"""Twitch GQL queries, persisted hashes, and browser-client POST with fallbacks."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import requests

from TwitchChannelPointsMiner.constants import BROWSER_CLIENT_ID, GQLOperations
from TwitchChannelPointsMiner.platform.paths import VAR_DIR, ensure_dirs

logger = logging.getLogger(__name__)

GQL_URL = GQLOperations.url
HASH_CACHE_FILE = VAR_DIR / "gql_hashes.json"

# Full mutation text (must match Twitch persisted document for hash).
REDEEM_COMMUNITY_POINTS_CUSTOM_REWARD = """
mutation RedeemCommunityPointsCustomReward($input: RedeemCommunityPointsCustomRewardInput!) {
  redeemCommunityPointsCustomReward(input: $input) {
    error { code message }
    redemption { id rewardID status }
  }
}
""".strip()

CHANNEL_POINTS_CUSTOM_REWARDS_LIST = GQLOperations.ChannelPointsCustomRewardsListQuery.strip()


def sha256_query(query: str) -> str:
    normalized = "\n".join(line.strip() for line in query.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_hash_cache() -> dict[str, str]:
    ensure_dirs()
    if not HASH_CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(HASH_CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_hash_cache(cache: dict[str, str]) -> None:
    ensure_dirs()
    HASH_CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def persisted_hash(operation_name: str, query: str) -> str:
    cache = _read_hash_cache()
    if operation_name in cache:
        return cache[operation_name]
    computed = sha256_query(query)
    cache[operation_name] = computed
    _write_hash_cache(cache)
    return computed


def _persisted_query_not_found(payload: dict) -> bool:
    for err in payload.get("errors") or []:
        msg = str(err.get("message") or "")
        if "PersistedQueryNotFound" in msg:
            return True
    return False


def browser_gql_headers(client) -> dict[str, str]:
    token = client.twitch_login.get_auth_token()
    return {
        "Authorization": f"OAuth {token}",
        "Client-Id": BROWSER_CLIENT_ID,
        "Client-Session-Id": client.client_session,
        "Client-Version": client.client_version,
        "User-Agent": client.user_agent,
        "X-Device-Id": client.device_id,
        "Content-Type": "application/json",
    }


def post_browser_gql(
    client,
    *,
    operation_name: str,
    variables: dict[str, Any],
    query: str | None = None,
    use_persisted: bool = True,
    timeout: int = 20,
) -> dict[str, Any]:
    """
    POST to gql.twitch.tv with browser Client-Id.
    Tries persisted query first; on PersistedQueryNotFound retries with full query body.
    """
    headers = browser_gql_headers(client)
    body: dict[str, Any] = {
        "operationName": operation_name,
        "variables": variables,
    }

    if use_persisted and query:
        body["extensions"] = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": persisted_hash(operation_name, query),
            }
        }
    elif query:
        body["query"] = query

    try:
        resp = requests.post(GQL_URL, json=body, headers=headers, timeout=timeout)
        payload = resp.json() if resp.content else {}
    except requests.RequestException as e:
        logger.warning("GQL %s request failed: %s", operation_name, e)
        return {"errors": [{"message": str(e)}]}

    if _persisted_query_not_found(payload) and query:
        logger.info("GQL %s: PersistedQueryNotFound — retry with full query", operation_name)
        retry = {
            "operationName": operation_name,
            "variables": variables,
            "query": query,
        }
        try:
            resp = requests.post(GQL_URL, json=retry, headers=headers, timeout=timeout)
            return resp.json() if resp.content else {}
        except requests.RequestException as e:
            return {"errors": [{"message": str(e)}]}

    return payload if isinstance(payload, dict) else {}


def redeem_mutation_body(input_payload: dict[str, Any]) -> dict[str, Any]:
    return {"input": input_payload}
