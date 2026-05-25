# Twitch Channel Points Miner — Production Dashboard

> **Полная документация:** [README.md](./README.md) · [CHANGELOG.md](./CHANGELOG.md)

## Architecture (V3.1)

| Layer | Path | Role |
|-------|------|------|
| Python miner | `TwitchChannelPointsMiner/` | Core farming logic |
| Control plane | `TwitchChannelPointsMiner/platform/` | Config, Twitch API, sessions, stats |
| API | `api_server.py` | Flask REST + static UI |
| Accounts | `config/accounts.json` | Per-bot JSON config |
| Factory | `platform/miner_factory.py` | Builds `TwitchChannelPointsMiner` from JSON |
| GQL | `platform/gql_queries.py` | Persisted hashes + `GQLClient` |
| Multi runner | `multi_session_runner.py` | **One OS process**, many bot threads |
| Session state | `var/sessions.json` | Desired running bots (reconciled) |
| Streamers | `config/streamers.json` | Global channel list |
| UI | `ui/` | React dashboard |

## Data flow

1. Add streamers in UI → `config/streamers.json`.
2. Create account in UI → `config/accounts.json`.
3. Start session → `POST /api/sessions/start` → entry in `var/sessions.json` → `multi_session_runner` starts thread for bot.
4. Status → `var/status/<username>.json` every 15s.
5. Stop → remove from `sessions.json` + `var/status/<user>.stop` flag.

## Run (development)

```bash
./venv/bin/pip install -r requirements.txt
./venv/bin/python api_server.py
```

```bash
cd ui && npm install && npm run dev
```

## Run (production)

```bash
cd ui && npm run build && cd ..
./venv/bin/python api_server.py
```

Optional: run multi runner manually (panel starts it automatically):

```bash
./venv/bin/python multi_session_runner.py
```

## Migration to V3.1

If you used **V3.0 or older** (screen per bot, `accounts/*.py`):

1. Pull code and rebuild UI.
2. Stop all legacy screens: `for s in $(screen -ls | grep twitch | awk '{print $1}'); do screen -S "$s" -X quit; done`
3. Start bots from the panel only.
4. Open **Аккаунты** → **переавторизовать** for each bot (fresh TV code).
5. Optional: remove obsolete `accounts/*.py` after confirming `config/accounts.json` has all bots.

## API (short)

- `GET /api/health` — `version: 3.1.0`
- `GET|POST|DELETE /api/streamers`
- `GET|POST /api/accounts` — JSON config
- `POST /api/sessions/start|stop|restart`
- `GET /api/rewards`, `POST /api/activate-reward`
- `GET|POST /api/chat`
- `POST /api/auth/device/start` — `{ username, force?: true }`

## Notes

- **Do not** use one screen per bot anymore; use multi runner.
- `session_runner.py --username X` is deprecated (single-bot debug only).
- GQL hash overrides: `var/gql_hashes.json`
