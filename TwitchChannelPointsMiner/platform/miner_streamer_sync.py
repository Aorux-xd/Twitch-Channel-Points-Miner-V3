"""Attach new streamers from config/streamers.json to a running miner session."""

from __future__ import annotations

import logging
import random
import time

from TwitchChannelPointsMiner.classes.Chat import ChatPresence, ThreadChat
from TwitchChannelPointsMiner.classes.entities.PubsubTopic import PubsubTopic
from TwitchChannelPointsMiner.classes.Exceptions import StreamerDoesNotExistException
from TwitchChannelPointsMiner.classes.Settings import Settings
from TwitchChannelPointsMiner.platform.events_log import log_event
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner
from TwitchChannelPointsMiner.utils import set_default_settings

logger = logging.getLogger(__name__)


def sync_streamers_to_miner(miner, account_username: str) -> list[str]:
    """Add streamers present in config but missing on miner.streamers."""
    if not getattr(miner, "running", False):
        return []
    streamers_list = getattr(miner, "streamers", None)
    if streamers_list is None:
        return []

    wanted = streamers_for_miner()
    current = {s.username for s in streamers_list}
    added: list[str] = []

    for streamer in wanted:
        login = streamer.username
        if login in current:
            continue
        try:
            time.sleep(random.uniform(0.2, 0.5))
            streamer.channel_id = miner.twitch.get_channel_id(login)
            streamer.settings = set_default_settings(
                streamer.settings, Settings.streamer_settings
            )
            streamer.settings.bet = set_default_settings(
                streamer.settings.bet, Settings.streamer_settings.bet
            )
            if streamer.settings.chat != ChatPresence.NEVER:
                streamer.irc_chat = ThreadChat(
                    miner.username,
                    miner.twitch.twitch_login.get_auth_token(),
                    login,
                )
            miner.twitch.load_channel_points_context(streamer)
            miner.twitch.check_streamer_online(streamer)
            streamers_list.append(streamer)
            current.add(login)
            added.append(login)

            ws_pool = getattr(miner, "ws_pool", None)
            if ws_pool is not None:
                ws_pool.submit(PubsubTopic("video-playback-by-id", streamer=streamer))
                if streamer.settings.follow_raid is True:
                    ws_pool.submit(PubsubTopic("raid", streamer=streamer))
                if streamer.settings.make_predictions is True:
                    ws_pool.submit(
                        PubsubTopic("predictions-channel-v1", streamer=streamer)
                    )
                if streamer.settings.claim_moments is True:
                    ws_pool.submit(
                        PubsubTopic("community-moments-channel-v1", streamer=streamer)
                    )
                if streamer.settings.community_goals is True:
                    ws_pool.submit(
                        PubsubTopic("community-points-channel-v1", streamer=streamer)
                    )

            log_event(
                "info",
                "streamer",
                f"Бот {account_username} подключил нового стримера {login} без перезапуска",
                account=account_username,
                streamer=login,
            )
        except StreamerDoesNotExistException:
            logger.info("sync: streamer %s does not exist", login)
        except Exception as e:
            logger.warning("sync streamer %s for %s: %s", login, account_username, e)

    return added
