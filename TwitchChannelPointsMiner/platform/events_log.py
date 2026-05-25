import json
import time
from pathlib import Path

from TwitchChannelPointsMiner.platform.paths import LOGS_DIR, ensure_dirs

EVENTS_FILE = LOGS_DIR / "platform_events.jsonl"


def log_event(
    level: str,
    category: str,
    message: str,
    *,
    account: str | None = None,
    streamer: str | None = None,
    points: int | None = None,
):
    ensure_dirs()
    row = {
        "ts": int(time.time()),
        "level": level,
        "category": category,
        "message": message,
        "account": account,
        "streamer": streamer,
        "points": points,
    }
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_events(limit: int = 500, category: str | None = None) -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            row = json.loads(line)
            if category and row.get("category") != category:
                continue
            out.append(row)
        except Exception:
            continue
    return out
