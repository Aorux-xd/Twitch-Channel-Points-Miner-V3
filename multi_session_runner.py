#!/usr/bin/env python3
"""
Единственная точка запуска ботов (V3.2).

  python multi_session_runner.py              # reconcile loop (production)
  python multi_session_runner.py --single USER  # отладка одного бота
"""

from __future__ import annotations

import argparse
import logging
import sys

from TwitchChannelPointsMiner.platform.multi_session_manager import (
    MultiSessionManager,
    _setup_runner_logging,
)
from TwitchChannelPointsMiner.platform.miner_factory import create_miner_from_config
from TwitchChannelPointsMiner.platform.account_store import get_account_config
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner


def run_single(username: str) -> int:
    _setup_runner_logging()
    cfg = get_account_config(username)
    if not cfg:
        print(f"No config/accounts.json entry for {username}", file=sys.stderr)
        return 1
    streamers = streamers_for_miner()
    if not streamers:
        print("No streamers in config/streamers.json", file=sys.stderr)
        return 2
    logging.getLogger(__name__).warning(
        "Single-bot debug mode for %s — not for production", username
    )
    miner = create_miner_from_config(username, cfg)
    miner.mine(streamers, followers=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Twitch Points Miner multi-session runner")
    parser.add_argument(
        "--single",
        metavar="USERNAME",
        help="Debug: run one bot in foreground (no reconcile loop)",
    )
    args = parser.parse_args()
    if args.single:
        return run_single(args.single.strip())
    MultiSessionManager().run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
