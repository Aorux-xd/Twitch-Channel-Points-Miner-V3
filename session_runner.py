"""Legacy single-bot runner. Prefer multi_session_runner.py (V3.1)."""

import argparse
import sys

from TwitchChannelPointsMiner.platform.account_store import get_account_config
from TwitchChannelPointsMiner.platform.miner_factory import create_miner_from_config
from TwitchChannelPointsMiner.platform.paths import ROOT
from TwitchChannelPointsMiner.platform.streamers_store import streamers_for_miner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    username = args.username.strip()

    cfg = get_account_config(username)
    if not cfg:
        print(
            f"No entry in config/accounts.json for {username}",
            file=sys.stderr,
        )
        return 1

    streamers = streamers_for_miner()
    if not streamers:
        print("No streamers in config/streamers.json", file=sys.stderr)
        return 2

    print(
        "Warning: single session_runner is deprecated. Use multi_session_runner.",
        file=sys.stderr,
    )
    miner = create_miner_from_config(username, cfg)
    miner.mine(streamers, followers=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
