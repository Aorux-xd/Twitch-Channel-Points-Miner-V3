# Changelog

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
