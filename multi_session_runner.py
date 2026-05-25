#!/usr/bin/env python3
"""Single process hosting multiple bot miners (see multi_session_manager.py)."""

import sys

from TwitchChannelPointsMiner.platform.multi_session_manager import MultiSessionManager


def main() -> int:
    MultiSessionManager().run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
