"""Build TwitchChannelPointsMiner instances from JSON account config (no .py per bot)."""

from __future__ import annotations

import logging
from typing import Any

from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.classes.Chat import ChatPresence
from TwitchChannelPointsMiner.classes.Settings import Priority
from TwitchChannelPointsMiner.classes.entities.Bet import (
    BetSettings,
    Condition,
    DelayMode,
    FilterCondition,
    OutcomeKeys,
    Strategy,
)
from TwitchChannelPointsMiner.classes.entities.Streamer import StreamerSettings
from TwitchChannelPointsMiner.logger import ColorPalette, LoggerSettings

logger = logging.getLogger(__name__)


def _bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return bool(v)


def _int(v: Any, default: int) -> int:
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def create_miner_from_config(username: str, config: dict[str, Any]) -> TwitchChannelPointsMiner:
    """Single factory for multi_session_runner — config from accounts.json only."""
    username = str(config.get("username") or username).strip()
    password = config.get("password") or None

    priority: list = []
    if _bool(config.get("priority_streak"), True):
        priority.append(Priority.STREAK)
    if _bool(config.get("priority_drops"), True):
        priority.append(Priority.DROPS)
    if _bool(config.get("priority_order"), True):
        priority.append(Priority.ORDER)
    if not priority:
        priority.append(Priority.ORDER)

    chat_raw = str(config.get("chat_presence") or "ONLINE").upper()
    try:
        chat_presence = getattr(ChatPresence, chat_raw)
    except AttributeError:
        chat_presence = ChatPresence.ONLINE

    bet_raw = str(config.get("bet_strategy") or "SMART").upper()
    try:
        bet_strategy = getattr(Strategy, bet_raw)
    except AttributeError:
        bet_strategy = Strategy.SMART

    return TwitchChannelPointsMiner(
        username=username,
        password=password,
        claim_drops_startup=_bool(config.get("claim_drops_startup"), False),
        enable_analytics=True,
        disable_ssl_cert_verification=False,
        disable_at_in_nickname=False,
        priority=priority,
        logger_settings=LoggerSettings(
            save=_bool(config.get("save_logs"), True),
            console_level=logging.INFO,
            console_username=True,
            auto_clear=True,
            time_zone="",
            file_level=logging.INFO,
            emoji=True,
            less=_bool(config.get("less_logs"), False),
            colored=True,
            color_palette=ColorPalette(),
        ),
        streamer_settings=StreamerSettings(
            make_predictions=_bool(config.get("make_predictions"), True),
            follow_raid=_bool(config.get("follow_raid"), True),
            claim_drops=_bool(config.get("claim_drops"), True),
            claim_moments=_bool(config.get("claim_moments"), True),
            watch_streak=_bool(config.get("watch_streak"), True),
            community_goals=False,
            chat=chat_presence,
            bet=BetSettings(
                strategy=bet_strategy,
                percentage=_int(config.get("bet_percentage"), 5),
                percentage_gap=20,
                max_points=_int(config.get("bet_max_points"), 50000),
                stealth_mode=True,
                delay_mode=DelayMode.FROM_END,
                delay=6,
                minimum_points=0,
                filter_condition=FilterCondition(
                    by=OutcomeKeys.TOTAL_USERS,
                    where=Condition.LTE,
                    value=800,
                ),
            ),
        ),
    )
