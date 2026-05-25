"""One-shot Twitch device login for a bot account (creates cookies/<user>.pkl)."""

import argparse
import sys

from TwitchChannelPointsMiner.classes.Twitch import Twitch
from TwitchChannelPointsMiner.utils import get_user_agent

from TwitchChannelPointsMiner.platform.auth_state import clear_auth_state, write_auth_state
from TwitchChannelPointsMiner.platform.paths import COOKIES_DIR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    username = args.username.strip()

    cookie_path = COOKIES_DIR / f"{username}.pkl"
    if cookie_path.exists():
        write_auth_state(username, {"status": "complete"})
        return 0

    write_auth_state(username, {"status": "starting"})
    try:
        client = Twitch(username, get_user_agent("CHROME"))
        if client.twitch_login.login_flow():
            client.twitch_login.save_cookies(client.cookies_file)
            write_auth_state(username, {"status": "complete"})
            return 0
        write_auth_state(
            username,
            {"status": "error", "message": "Не удалось войти в Twitch"},
        )
        return 1
    except Exception as e:
        write_auth_state(username, {"status": "error", "message": str(e)})
        return 1
    finally:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
