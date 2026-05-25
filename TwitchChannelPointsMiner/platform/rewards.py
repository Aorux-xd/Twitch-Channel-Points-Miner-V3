"""Activate (redeem) channel points custom rewards for one or many bot accounts."""

from __future__ import annotations

from TwitchChannelPointsMiner.platform.accounts import accounts_with_cookies
from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.twitch_gql import redeem_channel_reward


def activate_rewards(
    streamer_login: str,
    reward_id: str,
    session: str | None = None,
    *,
    text: str | None = None,
    reward_name: str | None = None,
) -> dict:
    streamer_login = streamer_login.strip().lower()
    accounts = accounts_with_cookies(session)
    if not accounts:
        return {
            "ok": False,
            "error": "Нет аккаунтов с cookie для активации",
            "results": [],
        }

    results = []
    ok_count = 0
    for username in accounts:
        row = redeem_channel_reward(
            streamer_login,
            reward_id,
            username,
            text_input=text,
        )
        entry = {
            "account": username,
            "ok": bool(row.get("ok")),
            "error": row.get("error"),
            "code": row.get("code"),
            "redemption_id": row.get("redemption_id"),
            "status": row.get("status"),
        }
        results.append(entry)
        if row.get("ok"):
            ok_count += 1
            log_event(
                "success",
                "reward",
                f"{username} активировал «{reward_name or reward_id}» на {streamer_login}",
                account=username,
                streamer=streamer_login,
            )
        else:
            log_event(
                "warning",
                "reward",
                f"{username}: не удалось активировать — {row.get('error')}",
                account=username,
                streamer=streamer_login,
            )

    return {
        "ok": ok_count > 0,
        "ok_count": ok_count,
        "total": len(results),
        "results": results,
    }
