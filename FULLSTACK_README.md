# Twitch Channel Points Miner — Production Dashboard

> **Полная документация:** [README.md](./README.md) · [CHANGELOG.md](./CHANGELOG.md)

## Architecture (V3.3)

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
4. Status → `var/status/<username>.json` every 15s; runner state → `var/multi_session_state.json`.
5. Stop → remove from `sessions.json` (reconciler stops thread) + optional `var/status/<user>.stop`.

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

## Migration to V3.3

From **V3.2**:

1. Pull + `cd ui && npm run build`
2. Restart API and multi runner (panel start is OK)
3. Review `config/settings.json` (replaces `rate_limits.json` + hardcoded TTLs)
4. Debug: `GET /api/sessions/debug` (`worker_details`, heartbeat)
5. Chat `WRONG_ACCOUNT` → re-auth that bot only (auto single restart)

From **V3.1** or older (screen per bot): see [CHANGELOG.md](./CHANGELOG.md) V3.2 migration, then steps above.

## API (short)

- `GET /api/health` — `version: 3.3.0`
- `GET /api/system` — CPU/RAM + `bot_resources` + multi runner
- `GET /api/sessions/debug` — desired vs workers + `worker_details`
- `GET|POST|DELETE /api/streamers`
- `GET|POST /api/accounts` — JSON config
- `POST /api/sessions/start|stop|restart`
- `GET /api/rewards`, `POST /api/activate-reward`
- `GET|POST /api/chat`
- `POST /api/auth/device/start` — `{ username, force?: true }`

## Notes

- Production runner: `multi_session_runner.py` only.
- Single-bot debug: `python multi_session_runner.py --single USERNAME`
- GQL hash overrides: `var/gql_hashes.json`
- Settings: `config/settings.json` (rate limits, cache TTL, runner)
