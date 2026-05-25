"""Central Twitch GQL: persisted hashes, query bodies, GQLClient with auto-retry."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

import requests

from TwitchChannelPointsMiner.constants import BROWSER_CLIENT_ID, CLIENT_ID
from TwitchChannelPointsMiner.platform.paths import VAR_DIR, ensure_dirs
from TwitchChannelPointsMiner.platform.rate_limit import GQL_LIMITER
from TwitchChannelPointsMiner.platform.settings import get_section

logger = logging.getLogger(__name__)

GQL_URL = "https://gql.twitch.tv/gql"
INTEGRITY_URL = "https://gql.twitch.tv/integrity"
HASH_CACHE_FILE = VAR_DIR / "gql_hashes.json"

# Official persisted SHA256 hashes (Twitch web/TV). Updated via var/gql_hashes.json overrides.
PERSISTED_HASHES: dict[str, str] = {
    "WithIsStreamLiveQuery": "04e46329a6786ff3a81c01c50bfa5d725902507a0deb83b0edbf7abe7a3716ea",
    "PlaybackAccessToken": "3093517e37e4f4cb48906155bcd894150aef92617939236d2508f3375ab732ce",
    "VideoPlayerStreamInfoOverlayChannel": "198492e0857f6aedead9665c81c5a06d67b25b58034649687124083ff288597d",
    "ClaimCommunityPoints": "46aaeebe02c99afdf4fc97c7c0cba964124bf6b0af229395f1f6d1feed05b3d0",
    "CommunityMomentCallout_Claim": "e2d67415aead910f7f9ceb45a77b750a1e1d9622c936d832328a0689e054db62",
    "DropsPage_ClaimDropRewards": "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930",
    "ChannelPointsContext": "1530a003a7d374b0380b79db0be0534f30ff46e61cffa2bc0e2468a909fbc024",
    "JoinRaid": "c6a332a86d1087fbbb1a8623aa01bd1313d2386e7c63be60fdb2d1901f01a4ae",
    "ModViewChannelQuery": "df5d55b6401389afb12d3017c9b2cf1237164220c8ef4ed754eae8188068a807",
    "Inventory": "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b",
    "MakePrediction": "b44682ecc88358817009f20e69d75081b1e58825bb40aa53d5dbadcc17c881d8",
    "ViewerDropsDashboard": "5a4da2ab3d5b47c9f9ce864e727b2cb346af1e3ea8b897fe8f704a97ff017619",
    "DropCampaignDetails": "f6396f5ffdde867a8f6f6da18286e4baf02e5b98d14689a69b5af320a4c7b7b8",
    "DropsHighlightService_AvailableDrops": "9a62a09bce5b53e26e64a671e530bc599cb6aab1e5ba3cbd5d85966d3940716f",
    "GetIDFromLogin": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca",
    "PersonalSections": "9fbdfb00156f754c26bde81eb47436dee146655c92682328457037da1a48ed39",
    "ChannelFollows": "eecf815273d3d949e5cf0085cc5084cd8a1b5b7b6f7990cf43cb0beadf546907",
    "UserPointsContribution": "23ff2c2d60708379131178742327ead913b93b1bd6f665517a6d9085b73f661f",
    "ContributeCommunityPointsCommunityGoal": "5774f0ea5d89587d73021a2e03c3c44777d903840c608754a1be519f51e37bb6",
}

FULL_QUERIES: dict[str, str] = {
    "RedeemCommunityPointsCustomReward": """
mutation RedeemCommunityPointsCustomReward($input: RedeemCommunityPointsCustomRewardInput!) {
  redeemCommunityPointsCustomReward(input: $input) {
    error { code message }
    redemption { id rewardID status }
  }
}
""".strip(),
    "ChannelPointsCustomRewardsList": """
query ChannelPointsCustomRewardsList($login: String!) {
  channel(name: $login) {
    communityPointsSettings {
      customRewards {
        id
        title
        prompt
        cost
        isEnabled
        isInStock
        isUserInputRequired
        defaultImage { url }
      }
    }
  }
}
""".strip(),
}


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


def persisted_hash(operation_name: str, query: str | None = None) -> str:
    """Override via var/gql_hashes.json; falls back to PERSISTED_HASHES."""
    overrides = _read_hash_cache()
    if operation_name in overrides:
        return overrides[operation_name]
    if operation_name in PERSISTED_HASHES:
        return PERSISTED_HASHES[operation_name]
    if query:
        computed = sha256_query(query)
        overrides[operation_name] = computed
        _write_hash_cache(overrides)
        return computed
    raise KeyError(f"No persisted hash for {operation_name}")


def persisted_payload(
    operation_name: str,
    variables: dict[str, Any] | None = None,
    *,
    extra: dict | None = None,
) -> dict[str, Any]:
    """Build GQL body for miner TV client (copy.deepcopy friendly)."""
    body: dict[str, Any] = {
        "operationName": operation_name,
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": persisted_hash(
                    operation_name, FULL_QUERIES.get(operation_name)
                ),
            }
        },
    }
    if variables is not None:
        body["variables"] = variables
    if extra:
        body.update(extra)
    return body


def _persisted_query_not_found(payload: dict) -> bool:
    for err in payload.get("errors") or []:
        if "PersistedQueryNotFound" in str(err.get("message") or ""):
            return True
    return False


_gql_client_pool: dict[tuple[int, bool], "GQLClient"] = {}
_gql_pool_lock = threading.Lock()


def get_gql_client(twitch_client, *, browser: bool = False) -> "GQLClient":
    """Reuse one GQLClient per Twitch instance + browser flag."""
    key = (id(twitch_client), browser)
    with _gql_pool_lock:
        client = _gql_client_pool.get(key)
        if client is None:
            client = GQLClient(twitch_client, browser=browser)
            _gql_client_pool[key] = client
        return client


def invalidate_gql_clients(twitch_client=None) -> None:
    with _gql_pool_lock:
        if twitch_client is None:
            _gql_client_pool.clear()
            return
        drop = [k for k in _gql_client_pool if k[0] == id(twitch_client)]
        for k in drop:
            _gql_client_pool.pop(k, None)


def shutdown_gql_clients() -> None:
    """Clear pooled GQL clients on multi-session runner shutdown."""
    invalidate_gql_clients(None)


_gql_settings = get_section("gql")
GQL_REQUEST_TIMEOUT = int(_gql_settings.get("request_timeout_sec", 20))


class GQLClient:
    """POST gql.twitch.tv with persisted-query fallback to full query text."""

    def __init__(self, twitch_client, *, browser: bool = False) -> None:
        self._client = twitch_client
        self._browser = browser

    def __enter__(self) -> "GQLClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def _headers(self) -> dict[str, str]:
        token = self._client.twitch_login.get_auth_token()
        client_id = BROWSER_CLIENT_ID if self._browser else CLIENT_ID
        h = {
            "Authorization": f"OAuth {token}",
            "Client-Id": client_id,
            "Client-Session-Id": self._client.client_session,
            "Client-Version": self._client.client_version,
            "User-Agent": self._client.user_agent,
            "X-Device-Id": self._client.device_id,
            "Content-Type": "application/json",
        }
        return h

    def post(
        self,
        operation_name: str,
        variables: dict[str, Any] | None = None,
        *,
        query: str | None = None,
        body: dict[str, Any] | None = None,
        use_persisted: bool = True,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        timeout = timeout if timeout is not None else GQL_REQUEST_TIMEOUT
        GQL_LIMITER.wait(f"gql:{operation_name}")

        if body is not None:
            payload_body = copy.deepcopy(body)
        else:
            payload_body = {"operationName": operation_name}
            if variables is not None:
                payload_body["variables"] = variables
            q = query or FULL_QUERIES.get(operation_name)
            if use_persisted and q:
                payload_body["extensions"] = {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": persisted_hash(operation_name, q),
                    }
                }
            elif q:
                payload_body["query"] = q

        try:
            resp = requests.post(
                GQL_URL, json=payload_body, headers=self._headers(), timeout=timeout
            )
            payload = resp.json() if resp.content else {}
        except requests.RequestException as e:
            logger.warning("GQL %s failed: %s", operation_name, e)
            return {"errors": [{"message": str(e)}]}

        if _persisted_query_not_found(payload):
            q = query or FULL_QUERIES.get(operation_name)
            if q:
                logger.info(
                    "GQL %s: PersistedQueryNotFound — full query retry",
                    operation_name,
                )
                retry = {
                    "operationName": operation_name,
                    "variables": variables or {},
                    "query": q,
                }
                try:
                    resp = requests.post(
                        GQL_URL, json=retry, headers=self._headers(), timeout=timeout
                    )
                    return resp.json() if resp.content else {}
                except requests.RequestException as e:
                    return {"errors": [{"message": str(e)}]}

        return payload if isinstance(payload, dict) else {}


def post_browser_gql(client, *, operation_name: str, variables: dict, query: str | None = None, **kw) -> dict:
    return get_gql_client(client, browser=True).post(
        operation_name, variables, query=query, **kw
    )


def post_tv_gql(client, body: dict) -> dict:
    """Primary TV-client GQL path (replaces direct requests in Twitch.py)."""
    op = body.get("operationName", "unknown")
    variables = body.get("variables")
    return get_gql_client(client, browser=False).post(
        op, variables, body=body, use_persisted=True
    )


def redeem_mutation_body(input_payload: dict[str, Any]) -> dict[str, Any]:
    return {"input": input_payload}


REDEEM_COMMUNITY_POINTS_CUSTOM_REWARD = FULL_QUERIES["RedeemCommunityPointsCustomReward"]
CHANNEL_POINTS_CUSTOM_REWARDS_LIST = FULL_QUERIES["ChannelPointsCustomRewardsList"]
