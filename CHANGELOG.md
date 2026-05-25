# Changelog

## [3.3.0] — 2026-05-25

### P1 — Multi-session stability

- **Reconciler** каждые **5 с**; немедленный reconcile при изменении `var/sessions.json` (mtime watcher + `notify_sessions_changed()` из API).
- Авто-restart упавших ботов: до **3 попыток** с backoff **5 / 15 / 45 с**; исключения в потоке не валят весь runner.
- Graceful shutdown: **SIGINT / SIGTERM / SIGQUIT** → `miner.end()` → финальный снимок `var/multi_session_state.json`.
- Per-bot **heartbeat** и `stale` в state; watcher потоков.

### P2 — Chat, monitoring, auth

- Массовая отправка чата: очередь + backpressure (`BACKPRESSURE` при переполнении).
- UI чата: время последнего сообщения, статус подключения, баннер **WRONG_ACCOUNT** → переавторизация.
- `GET /api/sessions/debug`: `worker_details` (uptime, last_error, memory est).
- `GET /api/system`: `bot_resources`, память/CPU multi runner.
- После re-auth — **restart только одного** бота (`restart_single_session`).

### P3 — Config & cleanup

- Единый **`config/settings.json`** (rate limits, TTL кэшей, runner, log rotation); legacy `rate_limits.json` подхватывается.
- `GQLClient` singleton (`get_gql_client`).
- Логи: `logs/multi_session_runner.log` + `logs/sessions/<user>.log`, ротация **5 MB × 3**.
- UI: убраны badge `screen`; менее агрессивный refresh meta/points (настраивается).

### Migration V3.2 → V3.3

1. `git pull` + `cd ui && npm run build`
2. Перезапустить `api_server` и `multi_session_runner` (или старт из панели)
3. Проверить `config/settings.json` (при необходимости скопировать из `config/rate_limits.json` в `rate_limits`)
4. `GET /api/sessions/debug` — heartbeat / retry meta
5. При `WRONG_ACCOUNT` в чате — **переавторизовать** конкретного бота (restart только его)

---

## [3.2.0] — 2026-05-24

### P1 — Multi-session & legacy cleanup

- **Reconciler** каждые 6 с: `var/sessions.json` (desired) ↔ реальные потоки; graceful shutdown по SIGINT/SIGTERM.
- Per-bot логи: `logs/sessions/<username>.log`, общий `logs/multi_session_runner.log`; снимок `var/multi_session_state.json`.
- Удалён `session_runner.py`; production — только `multi_session_runner.py` (`--single USER` для отладки).
- API/сессии без screen и без `accounts/*.py`; `ensure_accounts_from_cookies()` вместо миграции `.py`.
- **GQL:** `persisted_hash()` читает `var/gql_hashes.json`; все TV GQL через `GQLClient` / `post_tv_gql()`.

### P2 — Chat, auth, monitoring

- Буфер чата до 100 сообщений в API; улучшенные тексты `msg_rejected`, `RATE_LIMIT`, `WRONG_ACCOUNT`.
- После переавторизации — автоматический restart в multi-runner.
- `GET /api/sessions/debug` — desired + workers + runner PID.
- `GET /api/system` — `active_workers`, блок `multi_session`.

### P3

- TTL кэша наград **15 мин** (`REWARDS_TTL = 900`).
- Настраиваемые rate limits: `config/rate_limits.json`.
- События старт/стоп ботов в `platform_events.jsonl`.

### Migration V3.1 → V3.2

1. `git pull` + `cd ui && npm run build`
2. Остановить старые `twitch*` screen и прежний multi runner
3. `./venv/bin/python multi_session_runner.py` (или старт из панели)
4. Запустить ботов в UI; при проблемах чата — **переавторизовать** каждого бота

---

## [3.1.0] — 2026-05-24

### Architecture

- **Multi-session:** один процесс `multi_session_runner.py` вместо screen на каждого бота; состояние в `var/sessions.json`, reconcile каждые 5 с.
- **Аккаунты:** только `config/accounts.json` + `miner_factory.py`; удалён `account_builder.py`, поддержка `accounts/*.py` убрана из API/сессий.
- **GQL:** все persisted hashes в `gql_queries.py`, класс `GQLClient` с auto-retry при `PersistedQueryNotFound`; майнер использует `post_tv_gql()`.

### Improvements

- Кэш наград per-streamer (TTL 10 мин, `var/rewards_cache.json`).
- TTL meta/points: 120 s / 60 s; rate-limit для GQL.
- После **переавторизации** — автоматический `POST /api/sessions/restart`.
- Чат UI: статусы `sending` / `sent` / `partial` / `failed` / `rate_limited`.

### Migration V3.0 → V3.1

1. `git pull` + `cd ui && npm run build`
2. Остановите старые screen-сессии: `screen -ls` → quit `twitch*`
3. Запустите ботов из панели (поднимется `multi_session_runner`)
4. Убедитесь, что все боты есть в `config/accounts.json` (миграция из `.py` при старте API)
5. **Переавторизовать** каждого бота после обновления cookie-логики

---

## [3.0.0] — 2026-05-24

### Critical fixes

- **Chat:** `sender_id` берётся из `oauth2/validate` (совпадает с токеном), авто-исправление `persistent` в cookie, IRC+echo fallback в режиме «Все сессии», rate-limit между ботами.
- **Auth:** кнопка «переавторизовать» удаляет старый `.pkl` и запускает TV-код (`force: true`); раньше при существующем cookie код не запрашивался.
- **Redeem GQL:** persisted query + автоматический fallback на полный mutation при `PersistedQueryNotFound`; коды ошибок Twitch (`COOLDOWN`, `INSUFFICIENT_POINTS`, …) с русскими текстами.
- **`/api/activate-reward`:** поле `partial`, `fail_count`, `code` в каждом результате.

### Refactoring (foundation)

- **`config/accounts.json`** + `account_store.py` — конфиг ботов без генерации `accounts/*.py` (legacy `.py` по-прежнему поддерживается).
- **`miner_factory.py`** — единая фабрика `TwitchChannelPointsMiner` из JSON.
- **`gql_queries.py`** — GQL mutations/queries, SHA256 hashes, `post_browser_gql()`.
- **`rate_limit.py`** — лимиты для chat/redeem.
- **`session_runner.py`** — сначала JSON, затем fallback на `.py`.

### API

- Версия API: **3.0.0** (`/api/health`, `/api/system`).

### Deploy

```bash
git pull
cd ui && npm run build
# перезапуск api_server.py
# для каждого бота: Аккаунты → переавторизовать → код на twitch.tv/activate
```
