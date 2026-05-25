"""Lightweight Twitch connectivity probe (cached)."""

import concurrent.futures
import logging
import socket
import time

import requests

logger = logging.getLogger(__name__)

_CACHE_TTL = 45
_last_check = 0.0
_last_ok = False
_last_warn = 0.0


def _dns_resolves(host: str, timeout: float = 3.0) -> bool:
    def _resolve() -> bool:
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            return True
        except OSError:
            return False

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_resolve).result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return False


def twitch_network_ok(force: bool = False) -> bool:
    """True if Twitch hosts resolve and respond (best-effort)."""
    global _last_check, _last_ok, _last_warn
    now = time.time()
    if not force and now - _last_check < _CACHE_TTL:
        return _last_ok

    _last_check = now
    ok = _dns_resolves("gql.twitch.tv") and _dns_resolves("www.twitch.tv")
    if ok:
        try:
            resp = requests.head(
                "https://gql.twitch.tv/gql",
                timeout=4,
                allow_redirects=True,
            )
            ok = resp.status_code < 500
        except requests.RequestException:
            ok = False

    _last_ok = ok
    if not ok and now - _last_warn > 120:
        _last_warn = now
        logger.warning(
            "Twitch недоступен (DNS/сеть). Панель работает из кэша; "
            "проверьте интернет, DNS (8.8.8.8) и VPN/firewall."
        )
    return ok
