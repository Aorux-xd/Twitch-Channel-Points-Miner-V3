from pathlib import Path

from TwitchChannelPointsMiner.platform.paths import LOGS_DIR, ensure_dirs


def resolve_log_file(username: str) -> Path | None:
    """Find the active log file for an account."""
    ensure_dirs()
    primary = LOGS_DIR / f"{username}.log"
    if primary.exists():
        return primary

    candidates = sorted(
        LOGS_DIR.glob(f"{username}.*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def read_log_chunk(username: str, offset: int, max_bytes: int = 256 * 1024) -> dict:
    log_path = resolve_log_file(username)
    if not log_path:
        return {"chunk": "", "nextOffset": offset, "eof": True, "path": None}

    data = log_path.read_bytes()
    if offset < 0:
        offset = 0
    chunk = data[offset:]
    if len(chunk) > max_bytes:
        chunk = chunk[:max_bytes]
    next_offset = offset + len(chunk)
    return {
        "chunk": chunk.decode("utf-8", errors="replace"),
        "nextOffset": next_offset,
        "eof": next_offset >= len(data),
        "path": str(log_path.name),
    }
