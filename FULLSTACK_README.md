# Twitch Channel Points Miner — Production Dashboard

> **Полная документация:** [README.md](./README.md) — структура, API, screen/VPS, **повторяющийся код**, changelog, troubleshooting.

## Architecture

| Layer | Path | Role |
|-------|------|------|
| Python miner | `TwitchChannelPointsMiner/` | Core farming logic |
| Control plane | `TwitchChannelPointsMiner/platform/` | Config, Twitch API, sessions, stats |
| API | `api_server.py` | Flask REST + static UI |
| Accounts | `accounts/<user>.py` | Per-bot config (`create_miner` only) |
| Runner | `session_runner.py` | One entry point per bot process (`--username`) |
| Streamers | `config/streamers.json` | Global channel list for all bots |
| UI | `ui/` | React dashboard |

**Not used:** `run_panel/` (removed), sibling `Twitch-Points-UI/` (old clone).

## Data flow

1. Add streamers in UI → `config/streamers.json`.
2. Create account in UI → `accounts/<username>.py`.
3. Start session → `screen -dmS twitchN ./venv/bin/python session_runner.py --username …` → loads account → `mine(streamers)`.
4. Status → `var/status/<username>.json` every 15s.
5. Platform events → `logs/platform_events.jsonl`.
6. Dashboard points → GQL cache `var/points_cache.json`.
7. Miner analytics JSON → `logs/analytics/<username>/` (if enabled).

## Run (development)

```bash
py -m pip install -r requirements.txt
py api_server.py
```

```bash
cd ui && npm install && npm run dev
```

Open http://localhost:3000 (API proxied to :8000).

## Run (production)

```bash
cd ui && npm run build && cd ..
py api_server.py
```

Open http://localhost:8000

## VPS screen (legacy manager.py style)

```bash
screen -dmS twitch1 ./venv/bin/python session_runner.py --username YOUR_LOGIN
screen -ls | grep twitch
```

Panel uses the same command via `POST /api/sessions/start`. Old `miner1`…`miner14` from root `manager.py` are unrelated.

## VPS path migration (2026-05-24)

```bash
cd /path/to/Twitch-Channel-Points-Miner-v2
[ -d runtime ] && mv runtime var
mkdir -p logs/analytics
[ -d analytics ] && mv analytics/* logs/analytics/ 2>/dev/null; rmdir analytics 2>/dev/null
```

Restart `api_server.py` and miner screens after pulling.

## API (short)

- `GET /api/dashboard`, `/api/active-streams`
- `GET|POST|DELETE /api/streamers`
- `GET /api/accounts/schema`, `GET|POST /api/accounts`, `POST …/restore-config`
- `POST /api/sessions/start|stop` — `{ "accounts": ["user1"] }`
- `GET /api/rewards`, `POST /api/activate-reward` (`text` / `textInput` для наград с вводом)
- `GET|POST /api/chat` — IRC чат стримера
- `GET /api/logs?username=&offset=`

## Notes

- `accounts/*.py` = config only; **do not** duplicate per-user launchers.
- `run.py` = reference template; production = UI + `session_runner.py`.
- First login: device flow → `cookies/<username>.pkl`.
