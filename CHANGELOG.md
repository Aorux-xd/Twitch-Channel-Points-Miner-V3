# Changelog

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
