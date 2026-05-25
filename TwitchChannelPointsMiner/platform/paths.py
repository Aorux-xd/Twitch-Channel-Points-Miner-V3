from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COOKIES_DIR = ROOT / "cookies"
LOGS_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "config"
VAR_DIR = ROOT / "var"
ACCOUNTS_DIR = ROOT / "accounts"
STATUS_DIR = VAR_DIR / "status"
ANALYTICS_DIR = LOGS_DIR / "analytics"

STREAMERS_FILE = CONFIG_DIR / "streamers.json"
SESSIONS_FILE = VAR_DIR / "sessions.json"

# Back-compat alias for internal refactors
RUNTIME_DIR = VAR_DIR


def ensure_dirs():
    for d in (
        COOKIES_DIR,
        LOGS_DIR,
        CONFIG_DIR,
        VAR_DIR,
        ACCOUNTS_DIR,
        STATUS_DIR,
        ANALYTICS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
