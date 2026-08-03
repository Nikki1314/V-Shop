# Configuration

Settings are loaded from environment variables and optional `.env` via Pydantic Settings (`app/config.py`).

Never commit real secrets. `.env` is gitignored; use `.env.example` as a template.

## Required variables

| Variable | Type | Description |
|---|---|---|
| `BOT_TOKEN` | string | Telegram Bot API token from BotFather |
| `DATABASE_URL` | string | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `MANAGER_CHAT_ID` | int | Chat ID for new-order notifications (private user or group/supergroup) |

## Authorization

| Variable | Type | Default | Description |
|---|---|---|---|
| `ADMIN_IDS` | list of ints | `[]` | Telegram user IDs allowed to use `/admin` |

Formats accepted:

```env
ADMIN_IDS=123456789
ADMIN_IDS=123456789,987654321
ADMIN_IDS=[123456789, 987654321]
```

Empty `ADMIN_IDS` fail-closes: nobody gets the admin panel.

Admin IDs also receive new-order notifications in private chat (deduplicated with `MANAGER_CHAT_ID`).

## Application

| Variable | Type | Default | Description |
|---|---|---|---|
| `APP_ENV` | string | `development` | Environment name; `development` / `dev` / `local` enable SQL echo |
| `LOG_LEVEL` | string | `INFO` | Root logging level (`DEBUG`, `INFO`, `WARNING`, …) |
| `TELEGRAM_SSL_VERIFY` | bool | `true` | Verify TLS when calling `api.telegram.org` |

Set `TELEGRAM_SSL_VERIFY=false` only if a local network intercepts HTTPS. Never disable verification in production.

## Docker Compose extras

Compose can override DB credentials via:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_DB` | `vshop` | Database name |
| `POSTGRES_USER` | `vshop` | Database user |
| `POSTGRES_PASSWORD` | `vshop` | Database password |
| `POSTGRES_PORT` | `5432` | Host port published for Postgres |

The bot service forces:

```text
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

so the container always talks to the Compose `db` service by hostname.

## Example `.env` (local Docker)

```env
BOT_TOKEN=123456:AA...
DATABASE_URL=postgresql+asyncpg://vshop:vshop@db:5432/vshop
ADMIN_IDS=123456789
MANAGER_CHAT_ID=123456789
APP_ENV=development
LOG_LEVEL=INFO
TELEGRAM_SSL_VERIFY=true
```

## Example `.env` (local Python + Compose DB)

```env
BOT_TOKEN=123456:AA...
DATABASE_URL=postgresql+asyncpg://vshop:vshop@localhost:5432/vshop
ADMIN_IDS=123456789
MANAGER_CHAT_ID=-1001234567890
APP_ENV=development
LOG_LEVEL=DEBUG
TELEGRAM_SSL_VERIFY=true
```

## Finding chat IDs

- **Private user ID**: message [@userinfobot](https://t.me/userinfobot) or similar.
- **Group ID**: add the bot to the group, send a message, inspect updates, or use a helper bot. Group IDs are typically negative (e.g. `-100…`).
