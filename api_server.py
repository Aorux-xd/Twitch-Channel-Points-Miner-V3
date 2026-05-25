import hashlib
import logging
import os
import platform
import sys
import threading
import time

import psutil
from flask import Flask, Response, jsonify, request, send_from_directory

from TwitchChannelPointsMiner.platform import accounts as accounts_service
from TwitchChannelPointsMiner.platform import logs_util, stats, streamers_store
from TwitchChannelPointsMiner.platform.accounts import list_accounts
from TwitchChannelPointsMiner.platform.events_log import log_event, read_events
from TwitchChannelPointsMiner.platform.paths import LOGS_DIR, ROOT, ensure_dirs
from TwitchChannelPointsMiner.platform.sessions import load_sessions, start_sessions, stop_sessions
from TwitchChannelPointsMiner.platform.streamers_store import _base_entries, refresh_all_meta_background
from TwitchChannelPointsMiner.platform.network_util import twitch_network_ok
from TwitchChannelPointsMiner.platform.twitch_gql import fetch_channel_rewards

logger = logging.getLogger(__name__)

PANEL_USER = "root@admin"
PANEL_PASS = os.environ.get("PANEL_PASSWORD", "ADMIN123")
PANEL_TOKEN = hashlib.sha256(
    f"{PANEL_USER}:{PANEL_PASS}:twitch-miner-panel-v2".encode()
).hexdigest()


def _background_worker():
    while True:
        try:
            if not twitch_network_ok():
                time.sleep(50)
                continue
            entries = _base_entries()
            if entries:
                from TwitchChannelPointsMiner.platform.twitch_gql import refresh_streamers_meta_cache

                refresh_streamers_meta_cache(entries)
                accounts = [
                    a["username"]
                    for a in list_accounts()
                    if a.get("has_cookie")
                ]
                if accounts:
                    from TwitchChannelPointsMiner.platform.twitch_gql import refresh_points_cache

                    refresh_points_cache(
                        [e["login"] for e in entries], accounts[:3]
                    )
        except Exception as e:
            logger.warning("background refresh failed: %s", e)
        time.sleep(50)


def create_app():
    ensure_dirs()
    app = Flask(__name__, static_folder=None)

    @app.before_request
    def _panel_auth_guard():
        if not request.path.startswith("/api/"):
            return None
        if request.path in ("/api/health", "/api/login"):
            return None
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {PANEL_TOKEN}":
            return None
        return jsonify({"error": "Unauthorized"}), 401

    threading.Thread(target=_background_worker, daemon=True).start()
    if twitch_network_ok():
        refresh_all_meta_background()

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "version": "2.1.0",
                "twitch_online": twitch_network_ok(),
            }
        )

    @app.post("/api/login")
    def panel_login():
        payload = request.get_json(force=True, silent=True) or {}
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if username == PANEL_USER and password == PANEL_PASS:
            return jsonify({"ok": True, "token": PANEL_TOKEN, "username": PANEL_USER})
        return jsonify({"error": "Неверный логин или пароль"}), 401

    @app.get("/api/system")
    def system():
        boot = psutil.boot_time()
        uptime_s = int(time.time() - boot)
        mem = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.1)
        sessions = load_sessions()
        disk = psutil.disk_usage("/")
        return jsonify(
            {
                "cpu": f"{cpu_pct:.1f}%",
                "cpu_percent": round(cpu_pct, 1),
                "ram": f"{mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB",
                "ram_used_gb": round(mem.used / (1024**3), 2),
                "ram_total_gb": round(mem.total / (1024**3), 2),
                "ram_free_gb": round(mem.available / (1024**3), 2),
                "ram_percent": round(mem.percent, 1),
                "disk_percent": round(disk.percent, 1),
                "uptime": f"{uptime_s // 86400}d {(uptime_s % 86400) // 3600}h {(uptime_s % 3600) // 60}m",
                "uptime_seconds": uptime_s,
                "status": "Healthy",
                "active_sessions": len(sessions),
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": platform.platform(),
                "hostname": platform.node(),
                "os_name": platform.system(),
                "twitch_online": twitch_network_ok(),
                "api_version": "2.1.0",
            }
        )

    @app.get("/api/dashboard")
    def dashboard():
        force = request.args.get("refresh") == "1"
        return jsonify(stats.dashboard_stats(force=force))

    @app.get("/api/active-streams")
    def active_streams():
        return jsonify({"streams": stats.active_streams()})

    @app.get("/api/streamers")
    def streamers_list():
        try:
            if request.args.get("refresh") == "1":
                refresh_all_meta_background()
            return jsonify({"streamers": streamers_store.list_streamers(enrich=True)})
        except Exception as e:
            logger.exception("streamers_list failed: %s", e)
            return jsonify(
                {"streamers": streamers_store.list_streamers(enrich=False), "degraded": True}
            )

    @app.post("/api/streamers")
    def streamers_add():
        try:
            payload = request.get_json(force=True, silent=True) or {}
            login = str(payload.get("login") or "").strip()
            if not login:
                return jsonify({"error": "login is required"}), 400
            row = streamers_store.add_streamer(
                login=login,
                claim_drops=bool(payload.get("claim_drops", True)),
                high_priority=bool(payload.get("high_priority", False)),
            )
            return jsonify({"ok": True, "streamer": row})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.exception("streamers_add failed")
            return jsonify({"error": str(e)}), 500

    @app.delete("/api/streamers/<string:login>")
    def streamers_delete(login: str):
        streamers_store.remove_streamer(login)
        return jsonify({"ok": True})

    @app.get("/api/accounts/schema")
    def accounts_schema():
        return jsonify({"fields": accounts_service.account_schema()})

    @app.get("/api/accounts")
    def accounts_list():
        sessions = load_sessions()
        data = accounts_service.list_accounts(running=set(sessions.keys()))
        for row in data:
            meta = sessions.get(row["username"], {})
            row["pid"] = meta.get("pid")
            row["startedAt"] = meta.get("startedAt")
            row["screen"] = meta.get("screen")
        return jsonify({"accounts": data})

    @app.post("/api/accounts")
    def accounts_create():
        payload = request.get_json(force=True, silent=True) or {}
        try:
            created = accounts_service.create_account(payload)
            log_event(
                "info",
                "account",
                f"Добавлен бот {created['username']}",
                account=created["username"],
            )
            return jsonify({"ok": True, **created}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.exception("accounts_create failed")
            return jsonify({"error": str(e)}), 500

    @app.delete("/api/accounts/<string:username>")
    def accounts_delete(username: str):
        accounts_service.delete_account(username)
        log_event("info", "account", f"Удалён бот {username}", account=username)
        return jsonify({"ok": True})

    @app.post("/api/accounts/<string:username>/restore-config")
    def accounts_restore_config(username: str):
        try:
            result = accounts_service.restore_account_config(username)
            return jsonify({"ok": True, **result})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/auth/device/start")
    def auth_device_start():
        from TwitchChannelPointsMiner.platform.device_auth import start_device_auth

        payload = request.get_json(force=True, silent=True) or {}
        username = str(payload.get("username") or "").strip()
        if not username:
            return jsonify({"error": "username is required"}), 400
        force = bool(payload.get("force"))
        return jsonify(start_device_auth(username, force=force))

    @app.get("/api/auth/device/<string:username>")
    def auth_device_status(username: str):
        from TwitchChannelPointsMiner.platform.device_auth import get_device_auth_status

        return jsonify(get_device_auth_status(username))

    @app.post("/api/auth/device/cancel/<string:username>")
    def auth_device_cancel(username: str):
        from TwitchChannelPointsMiner.platform.device_auth import cancel_device_auth

        cancel_device_auth(username)
        return jsonify({"ok": True})

    @app.get("/api/rewards")
    def rewards_list():
        streamer = str(request.args.get("streamer") or "").strip()
        account = str(request.args.get("account") or "").strip() or None
        if not streamer:
            return jsonify({"error": "streamer is required"}), 400
        rewards = fetch_channel_rewards(streamer, account=account)
        return jsonify({"rewards": rewards})

    @app.get("/api/sessions")
    def sessions_list():
        return jsonify({"sessions": load_sessions()})

    @app.post("/api/sessions/start")
    def sessions_start():
        payload = request.get_json(force=True, silent=True) or {}
        usernames = payload.get("accounts") or []
        return jsonify(start_sessions(usernames))

    @app.post("/api/sessions/stop")
    def sessions_stop():
        payload = request.get_json(force=True, silent=True) or {}
        usernames = payload.get("accounts") or []
        return jsonify(stop_sessions(usernames))

    @app.get("/api/logs")
    def logs_tail():
        username = str(request.args.get("username") or "").strip()
        offset = int(request.args.get("offset") or 0)
        if not username:
            return jsonify({"error": "username is required"}), 400
        return jsonify(logs_util.read_log_chunk(username, offset))

    @app.get("/api/logs/download")
    def logs_download():
        username = str(request.args.get("username") or "").strip()
        if not username:
            return jsonify({"error": "username is required"}), 400
        log_path = logs_util.resolve_log_file(username)
        if not log_path:
            return jsonify({"error": "log not found"}), 404
        return send_from_directory(LOGS_DIR, log_path.name, as_attachment=True)

    @app.get("/api/events")
    def events_feed():
        category = request.args.get("category")
        return jsonify({"events": read_events(category=category or None)})

    @app.post("/api/activate-reward")
    def activate_reward():
        from TwitchChannelPointsMiner.platform.rewards import activate_rewards

        payload = request.get_json(force=True, silent=True) or {}
        streamer = str(payload.get("streamer") or "").strip().lower()
        reward_id = str(payload.get("rewardId") or "").strip()
        if not streamer or not reward_id:
            return jsonify({"error": "streamer and rewardId are required"}), 400

        session = str(payload.get("session") or "Все сессии").strip()
        text_raw = payload.get("text")
        if text_raw is None:
            text_raw = payload.get("textInput")
        text = str(text_raw).strip() if text_raw not in (None, "") else None
        reward_name = payload.get("rewardName")

        result = activate_rewards(
            streamer,
            reward_id,
            session=session,
            text=text,
            reward_name=str(reward_name) if reward_name else None,
        )
        return jsonify(result)

    @app.get("/api/chat")
    def chat_messages():
        streamer = str(request.args.get("streamer") or "").strip().lower()
        if not streamer:
            return jsonify({"error": "streamer is required"}), 400
        limit = min(int(request.args.get("limit") or 100), 400)
        from TwitchChannelPointsMiner.platform.chat_hub import get_chat_messages

        data = get_chat_messages(streamer, limit=limit)
        dbg = data.get("debug") or {}
        logger.debug(
            "GET /api/chat streamer=%s reader=%s msgs=%s joined=%s",
            streamer,
            data.get("reader"),
            len(data.get("messages") or []),
            dbg.get("reader_joined"),
        )
        return jsonify(data)

    @app.post("/api/chat")
    def chat_send():
        payload = request.get_json(force=True, silent=True) or {}
        streamer = str(payload.get("streamer") or "").strip().lower()
        text = str(payload.get("text") or "").strip()
        session = str(payload.get("session") or "Все сессии").strip()
        if not streamer or not text:
            return jsonify({"error": "streamer and text are required"}), 400
        from TwitchChannelPointsMiner.platform.chat_hub import send_chat_message

        data = send_chat_message(streamer, text, session=session)
        logger.info(
            "POST /api/chat streamer=%s session=%s ok=%s/%s text=%r",
            streamer,
            session,
            data.get("ok_count"),
            data.get("total"),
            text[:80],
        )
        return jsonify(data)

    @app.post("/api/follow")
    def follow_channel_route():
        payload = request.get_json(force=True, silent=True) or {}
        login = str(payload.get("login") or payload.get("streamer") or "").strip()
        session = str(payload.get("session") or "Все сессии").strip()
        if not login:
            return jsonify({"error": "login is required"}), 400
        from TwitchChannelPointsMiner.platform.follow_service import follow_accounts

        return jsonify(follow_accounts(login, session=session))

    ui_dist = ROOT / "ui" / "dist"

    @app.get("/")
    def root():
        if ui_dist.exists():
            return send_from_directory(ui_dist, "index.html")
        return jsonify({"message": "Build UI: cd ui && npm run build"})

    @app.get("/<path:filename>")
    def static_files(filename: str):
        # API routes are registered above; unknown /api/* must not return SPA HTML.
        if filename == "api" or filename.startswith("api/"):
            return jsonify({"error": "Not found"}), 404
        if ui_dist.exists():
            file_path = ui_dist / filename
            if file_path.exists() and file_path.is_file():
                return send_from_directory(ui_dist, filename)
            return send_from_directory(ui_dist, "index.html")
        return Response("UI not built", status=404, mimetype="text/plain")

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    app.run(host=host, port=port, threaded=True)
