"""IRC chat hub for the web panel: read channel messages and send as bot accounts."""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field

import requests
from irc.bot import SingleServerIRCBot

from TwitchChannelPointsMiner.constants import CLIENT_ID, IRC, IRC_PORT
from TwitchChannelPointsMiner.platform.accounts import accounts_with_cookies, list_account_usernames
from TwitchChannelPointsMiner.platform.paths import COOKIES_DIR
from TwitchChannelPointsMiner.platform.twitch_gql import get_twitch

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_CHANNEL = 400
DEDUPE_WINDOW_SEC = 3.0
JOIN_TIMEOUT_SEC = 15.0
ECHO_VERIFY_SEC = 4.0
MAX_SEND_WORKERS = 8
BULK_SEND_DELAY_SEC = 1.2
BULK_ECHO_VERIFY_SEC = 3.0
BULK_IRC_FALLBACK_CODES = frozenset(
    {"msg_rejected", "RATE_LIMIT", "HTTP", "MISSING_SCOPE", "AUTH", "DROPPED", "HELIX_FAIL"}
)
HELIX_SCOPE_HINT = (
    "нужен scope user:write:chat — удалите cookies/<бот>.pkl и "
    "переавторизуйте бота (TV activate на twitch.tv/activate)"
)


def _helix_error_ru(code: str | None, raw: str | None) -> str:
    """Понятное описание ошибки Helix для панели."""
    raw_l = (raw or "").lower()
    if code == "WRONG_ACCOUNT":
        return (
            raw
            or "cookie не совпадает с логином бота — переавторизуйте с правильного аккаунта"
        )
    if code == "msg_rejected":
        return (
            "Twitch отклонил сообщение (msg_rejected): проверьте бан в чате, "
            "email/телефон, или переавторизуйте бота"
        )
    if code == "RATE_LIMIT":
        return "лимит Twitch — подождите 3–5 секунд"
    if code == "MISSING_SCOPE" or "user:write:chat" in (raw or ""):
        return HELIX_SCOPE_HINT
    if "too quickly" in raw_l:
        return "слишком частая отправка — подождите 2–3 сек и повторите"
    if code == "AUTH":
        return raw or "токен недействителен — переавторизуйте бота"
    return raw or "не удалось отправить"

BADGE_LABELS = {
    "broadcaster": "Создатель",
    "moderator": "Модератор",
    "vip": "VIP",
    "lead_moderator": "Ведущий мод",
    "founder": "Основатель",
    "subscriber": "Подписчик",
    "premium": "Prime",
    "staff": "Staff",
    "admin": "Админ",
    "partner": "Партнёр",
    "sub_gifter": "Даритель",
    "turbo": "Turbo",
    "clips-leader": "Клипы",
}


def _tags_dict(tags) -> dict[str, str]:
    if isinstance(tags, dict):
        return {str(k): str(v) for k, v in tags.items() if v is not None}
    if isinstance(tags, list):
        out: dict[str, str] = {}
        for item in tags:
            if isinstance(item, dict) and item.get("key"):
                val = item.get("value")
                out[str(item["key"])] = "" if val is None else str(val)
        return out
    return {}


def _parse_badges(tags) -> list[dict]:
    raw = _tags_dict(tags).get("badges") or ""
    if not raw:
        return []
    out = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part or "/" not in part:
            continue
        kind, version = part.split("/", 1)
        label = BADGE_LABELS.get(kind, kind.replace("_", " ").title())
        if kind == "subscriber" and version.isdigit():
            label = f"Подписчик {version}"
        out.append({"type": kind, "version": version, "label": label})
    return out


def _display_name(tags, nick: str) -> str:
    td = _tags_dict(tags)
    if td.get("display-name"):
        return str(td["display-name"])
    return nick


@dataclass
class ChatMessage:
    id: str
    streamer: str
    user: str
    text: str
    ts: float
    display_name: str = ""
    badges: list[dict] = field(default_factory=list)
    color: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class _PanelIRC(SingleServerIRCBot):
    """
    Twitch IRC: JOIN on WELCOME (same as miner ClientIRC).
    Outgoing PRIVMSG is queued and sent inside the reactor thread.
    """

    def __init__(
        self,
        username: str,
        token: str,
        streamer: str,
        on_message,
        *,
        capture: bool = True,
    ):
        self._streamer = streamer.lower()
        self._on_message = on_message
        self._capture = capture
        self._channel = f"#{self._streamer}"
        self.__active = False
        self._join_ready = threading.Event()
        self._outbox: queue.Queue[tuple[str, threading.Event, list[bool]]] = queue.Queue()
        self._last_notice: str | None = None
        nick = username.lower().strip()
        super().__init__(
            [(IRC, IRC_PORT, f"oauth:{token}")],
            nick,
            nick,
        )

    def on_welcome(self, client, event):
        try:
            client.cap("REQ", "twitch.tv/tags twitch.tv/commands")
        except Exception:
            pass
        client.join(self._channel)

    def on_cap(self, client, event):
        args = " ".join(event.arguments or [])
        if "twitch.tv/tags" in args:
            client.cap("ACK", "twitch.tv/tags")
        if "twitch.tv/commands" in args:
            client.cap("ACK", "twitch.tv/commands")

    def on_join(self, connection, event):
        if (event.target or "").lower() == self._channel:
            self._join_ready.set()

    def on_notice(self, connection, event):
        try:
            msg = event.arguments[0] if event.arguments else ""
            self._last_notice = str(msg)
            logger.warning(
                "chat IRC NOTICE %s on %s: %s",
                self._nickname,
                self._channel,
                msg,
            )
        except Exception:
            pass

    def on_pubmsg(self, connection, event):
        if not self._capture:
            return
        try:
            tags = getattr(event, "tags", None)
            nick = event.source.split("!", 1)[0]
            text = event.arguments[0] if event.arguments else ""
            self._on_message(self._streamer, nick, text, tags=tags)
        except Exception as e:
            logger.debug("chat on_pubmsg: %s", e)

    def _flush_outbox(self) -> None:
        while True:
            try:
                text, done_ev, ok_box = self._outbox.get_nowait()
            except queue.Empty:
                break
            if self._join_ready.is_set():
                try:
                    self.connection.privmsg(self._channel, text)
                    ok_box[0] = True
                except Exception as e:
                    logger.warning("chat privmsg %s: %s", self._channel, e)
            done_ev.set()

    def send_on_connection(self, text: str, timeout: float = JOIN_TIMEOUT_SEC) -> bool:
        """Thread-safe: schedule PRIVMSG on the IRC reactor thread."""
        text = (text or "").strip()
        if not text:
            return False
        if not self._join_ready.wait(timeout=timeout):
            logger.warning("chat send: join timeout for %s", self._channel)
            return False
        done_ev = threading.Event()
        ok_box: list[bool] = [False]
        self._outbox.put((text, done_ev, ok_box))
        if not done_ev.wait(timeout=timeout):
            logger.warning("chat send: outbox timeout for %s", self._channel)
            return False
        return ok_box[0]

    def start_loop(self):
        self.__active = True
        self._join_ready.clear()
        self._connect()
        while self.__active:
            try:
                self._flush_outbox()
                self.reactor.process_once(timeout=0.2)
                time.sleep(0.01)
            except Exception as e:
                logger.error("chat irc loop: %s", e)

    def stop(self):
        self.__active = False
        try:
            self.connection.disconnect("panel chat stop")
        except Exception:
            pass


class _ReaderThread(threading.Thread):
    def __init__(self, streamer: str, account: str, irc: _PanelIRC):
        super().__init__(daemon=True, name=f"chat-read-{streamer}")
        self.streamer = streamer
        self.account = account
        self.irc = irc

    def run(self):
        try:
            self.irc.start_loop()
        except Exception as e:
            logger.warning("chat reader %s stopped: %s", self.streamer, e)


def _oauth_validate(token: str) -> dict | None:
    try:
        resp = requests.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"OAuth {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return None


def _oauth_user_id(token: str) -> str | None:
    data = _oauth_validate(token)
    if not data:
        return None
    uid = data.get("user_id")
    return str(uid) if uid is not None else None


def _resolve_sender_id(client, account: str) -> str | None:
    """sender_id must match the Bearer token; cookie 'persistent' can be stale."""
    token = client.twitch_login.get_auth_token()
    if not token:
        return None
    validated = _oauth_validate(token)
    oauth_uid = (
        str(validated["user_id"])
        if validated and validated.get("user_id") is not None
        else None
    )
    if not oauth_uid:
        legacy = client.twitch_login.get_user_id()
        return str(legacy) if legacy is not None else None

    token_login = (validated.get("login") or "").lower()
    if token_login and token_login != account.lower():
        logger.error(
            "chat cookie login mismatch %s: token is for %s",
            account,
            token_login,
        )
        return None

    persistent = client.twitch_login.get_cookie_value("persistent")
    if persistent is not None:
        try:
            persistent_id = str(int(str(persistent).split("%")[0]))
        except (TypeError, ValueError):
            persistent_id = str(persistent)
        if persistent_id != oauth_uid:
            logger.warning(
                "chat cookie user_id mismatch %s: persistent=%s oauth=%s — fixing pickle",
                account,
                persistent_id,
                oauth_uid,
            )
            for cookie in client.twitch_login.cookies:
                if cookie.get("name") == "persistent":
                    cookie["value"] = oauth_uid
            try:
                client.twitch_login.save_cookies(client.cookies_file)
            except Exception as e:
                logger.warning("chat could not save fixed cookie for %s: %s", account, e)
    return oauth_uid


def _helix_send(account: str, streamer: str, text: str) -> dict:
    """Twitch Helix Send Chat Message — returns real is_sent / drop_reason."""
    client = get_twitch(account)
    if not client:
        return {"ok": False, "method": "helix", "error": "нет cookie / login", "code": "NO_AUTH"}

    broadcaster_id = None
    try:
        from TwitchChannelPointsMiner.platform.twitch_gql import _channel_id

        broadcaster_id = _channel_id(client, streamer)
    except Exception:
        pass
    token = client.twitch_login.get_auth_token()
    sender_id = _resolve_sender_id(client, account)
    if not token:
        return {"ok": False, "method": "helix", "error": "нет auth-token", "code": "NO_AUTH"}
    if not sender_id:
        validated = _oauth_validate(token)
        token_login = (validated or {}).get("login")
        if token_login and token_login.lower() != account.lower():
            return {
                "ok": False,
                "method": "helix",
                "error": (
                    f"cookie от @{token_login}, а файл {account}.pkl — "
                    "нажмите «переавторизовать» и введите код с нужного аккаунта"
                ),
                "code": "WRONG_ACCOUNT",
            }
        return {"ok": False, "method": "helix", "error": "нет channel/sender id", "code": "NO_ID"}
    if not broadcaster_id:
        return {"ok": False, "method": "helix", "error": "не найден канал", "code": "NO_CHANNEL"}

    try:
        resp = requests.post(
            "https://api.twitch.tv/helix/chat/messages",
            json={
                "broadcaster_id": broadcaster_id,
                "sender_id": sender_id,
                "message": text,
            },
            headers={
                "Client-ID": CLIENT_ID,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        body = resp.json() if resp.content else {}
    except requests.RequestException as e:
        return {"ok": False, "method": "helix", "error": str(e), "code": "NETWORK"}

    if resp.status_code == 401:
        msg = body.get("message") or "Unauthorized"
        if "user:write:chat" in msg:
            return {
                "ok": False,
                "method": "helix",
                "error": HELIX_SCOPE_HINT,
                "code": "MISSING_SCOPE",
            }
        return {"ok": False, "method": "helix", "error": msg, "code": "AUTH"}

    if resp.status_code not in (200, 204):
        raw = body.get("message") or f"HTTP {resp.status_code}"
        code = "RATE_LIMIT" if resp.status_code == 429 else "HTTP"
        return {
            "ok": False,
            "method": "helix",
            "error": _helix_error_ru(code, raw),
            "code": code,
            "error_raw": raw,
        }

    row = (body.get("data") or [{}])[0] if isinstance(body.get("data"), list) else {}
    if row.get("is_sent"):
        return {
            "ok": True,
            "method": "helix",
            "message_id": row.get("message_id"),
            "error": None,
        }

    drop = row.get("drop_reason") or {}
    drop_code = drop.get("code") or "DROPPED"
    drop_msg = drop.get("message") or drop_code
    return {
        "ok": False,
        "method": "helix",
        "error": _helix_error_ru(drop_code, str(drop_msg)),
        "code": drop_code,
        "error_raw": str(drop_msg),
    }


def _send_once(account: str, token: str, streamer: str, text: str) -> bool:
    """Short-lived IRC connection: connect → JOIN → PRIVMSG → disconnect."""
    text = text.strip()
    if not text:
        return False

    ok_box: list[bool] = [False]
    done = threading.Event()
    irc = _PanelIRC(account, token, streamer, lambda *_a, **_k: None, capture=False)

    def run():
        try:
            irc.__active = True
            irc._join_ready.clear()
            irc._connect()
            deadline = time.time() + JOIN_TIMEOUT_SEC
            while time.time() < deadline and irc.__active:
                irc._flush_outbox()
                irc.reactor.process_once(timeout=0.2)
                if irc._join_ready.is_set():
                    try:
                        irc.connection.privmsg(irc._channel, text)
                        ok_box[0] = True
                    except Exception as e:
                        logger.warning("send_once privmsg %s: %s", account, e)
                    break
                time.sleep(0.01)
        except Exception as e:
            logger.warning("send_once %s: %s", account, e)
        finally:
            try:
                irc.stop()
            except Exception:
                pass
            done.set()

    threading.Thread(target=run, daemon=True).start()
    done.wait(timeout=JOIN_TIMEOUT_SEC + 5)
    return ok_box[0]


class ChatHub:
    def __init__(self):
        self._lock = threading.RLock()
        self._messages: dict[str, deque[ChatMessage]] = {}
        self._readers: dict[str, _ReaderThread] = {}
        self._reader_irc: dict[str, _PanelIRC] = {}

    def _append(
        self,
        streamer: str,
        user: str,
        text: str,
        *,
        tags: dict | None = None,
    ) -> None:
        streamer = streamer.lower()
        text = text or ""
        user = user or ""
        now = time.time()
        badges = _parse_badges(tags)
        display = _display_name(tags, user)
        color = _tags_dict(tags).get("color")

        with self._lock:
            if streamer not in self._messages:
                self._messages[streamer] = deque(maxlen=MAX_MESSAGES_PER_CHANNEL)
            q = self._messages[streamer]
            if q:
                last = q[-1]
                if (
                    last.user.lower() == user.lower()
                    and last.text == text
                    and now - last.ts < DEDUPE_WINDOW_SEC
                ):
                    return
            q.append(
                ChatMessage(
                    id=str(uuid.uuid4()),
                    streamer=streamer,
                    user=user,
                    text=text,
                    ts=now,
                    display_name=display,
                    badges=badges,
                    color=color,
                )
            )

    def _auth_token(self, account: str) -> str | None:
        client = get_twitch(account)
        if not client:
            return None
        return client.twitch_login.get_auth_token()

    def ensure_reader(self, streamer: str, account: str | None = None) -> str | None:
        streamer = streamer.strip().lower()
        if not streamer:
            return None

        with self._lock:
            if streamer in self._readers and self._readers[streamer].is_alive():
                current = self._readers[streamer].account
                if not account or account == current:
                    return current

        pick = account
        if not pick or not (COOKIES_DIR / f"{pick}.pkl").exists():
            for u in list_account_usernames():
                if (COOKIES_DIR / f"{u}.pkl").exists():
                    pick = u
                    break
        if not pick:
            return None

        token = self._auth_token(pick)
        if not token:
            return None

        with self._lock:
            old = self._readers.get(streamer)
            if old and old.is_alive() and old.account == pick:
                return old.account
            if old and old.is_alive():
                try:
                    old.irc.stop()
                except Exception:
                    pass

        irc = _PanelIRC(pick, token, streamer, self._append, capture=True)
        thread = _ReaderThread(streamer, pick, irc)
        with self._lock:
            self._readers[streamer] = thread
            self._reader_irc[streamer] = irc
        thread.start()
        return pick

    def get_messages(self, streamer: str, limit: int = 100) -> list[dict]:
        streamer = streamer.strip().lower()
        self.ensure_reader(streamer)
        with self._lock:
            items = list(self._messages.get(streamer, []))
        if limit > 0:
            items = items[-limit:]
        return [m.to_dict() for m in items]

    def _wait_echo(
        self, streamer: str, account: str, text: str, *, timeout_sec: float | None = None
    ) -> tuple[bool, str]:
        """Confirm message appeared on reader IRC (same channel)."""
        streamer = streamer.lower()
        account_l = account.lower()
        text = text.strip()
        deadline = time.time() + (timeout_sec if timeout_sec is not None else ECHO_VERIFY_SEC)
        while time.time() < deadline:
            with self._lock:
                for m in self._messages.get(streamer, []):
                    if m.user.lower() == account_l and m.text == text:
                        return True, "echo"
            time.sleep(0.25)

        notice = None
        with self._lock:
            irc = self._reader_irc.get(streamer)
            if irc:
                notice = irc._last_notice
        if notice:
            return False, f"Twitch IRC: {notice}"
        return False, HELIX_SCOPE_HINT

    def _send_irc(self, streamer: str, account: str, text: str) -> bool:
        with self._lock:
            reader_irc = self._reader_irc.get(streamer)
            reader_account = (
                self._readers[streamer].account
                if streamer in self._readers
                else None
            )

        if reader_irc and reader_account == account:
            if reader_irc:
                reader_irc._last_notice = None
            return reader_irc.send_on_connection(text)

        token = self._auth_token(account)
        if not token:
            return False
        return _send_once(account, token, streamer, text)

    def _try_irc_send(
        self, streamer: str, account: str, text: str, *, echo_sec: float
    ) -> dict:
        if not self._send_irc(streamer, account, text):
            return {
                "account": account,
                "ok": False,
                "method": "irc",
                "error": "IRC join/PRIVMSG не удался",
                "code": "IRC_FAIL",
            }
        verified, err = self._wait_echo(
            streamer, account, text, timeout_sec=echo_sec
        )
        if verified:
            logger.info("chat irc+echo ok %s -> #%s", account, streamer)
            return {"account": account, "ok": True, "method": "irc", "error": None}
        return {
            "account": account,
            "ok": False,
            "method": "irc",
            "error": err,
            "code": "NO_ECHO",
        }

    def _send_one(self, streamer: str, account: str, text: str, *, bulk: bool) -> dict:
        """Send from one bot: Helix first, IRC+echo fallback when needed."""
        from TwitchChannelPointsMiner.platform.rate_limit import CHAT_SEND_LIMITER

        CHAT_SEND_LIMITER.wait(f"chat:{account}")

        helix = _helix_send(account, streamer, text)
        if helix.get("ok"):
            logger.info(
                "chat helix ok %s -> #%s id=%s",
                account,
                streamer,
                helix.get("message_id"),
            )
            return {
                "account": account,
                "ok": True,
                "method": "helix",
                "error": None,
            }

        helix_code = helix.get("code")
        err_text = helix.get("error") or "не удалось отправить"

        try_irc = helix_code in ("MISSING_SCOPE", "AUTH") or (
            bulk and helix_code in BULK_IRC_FALLBACK_CODES
        )
        if try_irc:
            irc_row = self._try_irc_send(
                streamer,
                account,
                text,
                echo_sec=BULK_ECHO_VERIFY_SEC if bulk else ECHO_VERIFY_SEC,
            )
            if irc_row.get("ok"):
                return irc_row
            if bulk:
                return {
                    **irc_row,
                    "error": irc_row.get("error") or err_text,
                }

        if bulk:
            return {
                "account": account,
                "ok": False,
                "method": "helix",
                "error": err_text,
                "code": helix_code or "HELIX_FAIL",
            }

        if helix_code not in ("MISSING_SCOPE", "AUTH"):
            return {
                "account": account,
                "ok": False,
                "method": "helix",
                "error": err_text,
                "code": helix_code,
            }

        return self._try_irc_send(streamer, account, text, echo_sec=ECHO_VERIFY_SEC)

    def send_message(
        self, streamer: str, text: str, accounts: list[str]
    ) -> list[dict]:
        streamer = streamer.strip().lower()
        text = text.strip()
        if not accounts:
            return []

        bulk = len(accounts) > 1
        results: list[dict] = []

        if bulk:
            for i, acc in enumerate(accounts):
                if i > 0:
                    time.sleep(BULK_SEND_DELAY_SEC)
                try:
                    results.append(self._send_one(streamer, acc, text, bulk=True))
                except Exception as e:
                    logger.warning("chat send %s: %s", acc, e)
                    results.append(
                        {
                            "account": acc,
                            "ok": False,
                            "error": str(e),
                            "code": "WORKER",
                        }
                    )
            return results

        workers = min(MAX_SEND_WORKERS, len(accounts))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._send_one, streamer, acc, text, bulk=False): acc
                for acc in accounts
            }
            for fut in as_completed(futures):
                acc = futures[fut]
                try:
                    results.append(fut.result())
                except Exception as e:
                    logger.warning("chat send worker %s: %s", acc, e)
                    results.append(
                        {
                            "account": acc,
                            "ok": False,
                            "error": str(e),
                            "code": "WORKER",
                        }
                    )

        order = {a: i for i, a in enumerate(accounts)}
        results.sort(key=lambda r: order.get(r.get("account", ""), 999))
        return results


_hub = ChatHub()


def _chat_status(streamer: str) -> dict:
    streamer = streamer.strip().lower()
    with _hub._lock:
        thread = _hub._readers.get(streamer)
        alive = thread is not None and thread.is_alive()
        reader = thread.account if alive else None
        joined = False
        if streamer in _hub._reader_irc:
            joined = _hub._reader_irc[streamer]._join_ready.is_set()
        buf = len(_hub._messages.get(streamer, []))
    return {
        "reader": reader,
        "reader_alive": alive,
        "reader_joined": joined,
        "buffer_messages": buf,
    }


def get_chat_messages(streamer: str, limit: int = 100) -> dict:
    account = _hub.ensure_reader(streamer)
    status = _chat_status(streamer)
    if not account:
        return {
            "streamer": streamer.lower(),
            "messages": [],
            "reader": None,
            "error": "нет аккаунта с cookie для чтения чата",
            "debug": status,
        }
    messages = _hub.get_messages(streamer, limit=limit)
    status = _chat_status(streamer)
    return {
        "streamer": streamer.lower(),
        "messages": messages,
        "reader": account,
        "debug": status,
    }


def send_chat_message(
    streamer: str, text: str, session: str | None = None
) -> dict:
    streamer = streamer.strip().lower()
    text = (text or "").strip()
    if not streamer or not text:
        return {"ok": False, "error": "streamer и text обязательны", "results": []}

    accounts = accounts_with_cookies(session)
    if not accounts:
        return {"ok": False, "error": "нет аккаунтов с cookie", "results": []}

    session_key = (session or "").strip()
    if session_key and session_key not in ("Все сессии", "__all__", "all"):
        _hub.ensure_reader(streamer, session_key)
    else:
        _hub.ensure_reader(streamer)
    results = _hub.send_message(streamer, text, accounts)
    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    out = {
        "ok": ok_count > 0,
        "partial": ok_count > 0 and fail_count > 0,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "total": len(results),
        "results": results,
        "streamer": streamer,
        "session": session_key or "Все сессии",
        "accounts": accounts,
        "debug": _chat_status(streamer),
    }
    logger.info(
        "chat POST #%s session=%s ok=%s/%s",
        streamer,
        out["session"],
        ok_count,
        len(results),
    )
    return out
