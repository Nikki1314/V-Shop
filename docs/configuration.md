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
| `APP_TIMEZONE` | string | `Europe/Berlin` | IANA zone used for statistics month boundaries |
| `CURRENCY_SYMBOL` | string | `€` | Symbol shown beside money figures on the statistics dashboard |

Set `TELEGRAM_SSL_VERIFY=false` only if a local network intercepts HTTPS. Never disable verification in production.

`APP_TIMEZONE` decides when a reporting month starts and ends. With the default,
an order placed at 00:30 Berlin time on 1 September belongs to September even
though it is still 31 August in UTC. An unrecognised zone name does not stop the
bot: it logs and falls back to `Europe/Berlin`, then to UTC. The zone database
ships with the `tzdata` package (a pinned dependency), so the value resolves the
same way on Windows, Alpine and Debian.

`CURRENCY_SYMBOL` sets the symbol only; where it sits and how the number is
punctuated follow the reader's language — `€1,234.56` in English, `1.234,56 €`
in German, `1 234,56 €` in Russian and Ukrainian. Those conventions live in the
`format` section of each locale catalog.

## Docker Compose extras

Compose can override DB credentials via:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_DB` | `vshop` | Database name |
| `POSTGRES_USER` | `vshop` | Database user |
| `POSTGRES_PASSWORD` | `vshop` | Database password |
| `POSTGRES_PORT` | `5432` | Host port published for Postgres |
| `POSTGRES_VOLUME_NAME` | `vshop_pgdata` | **Docker volume holding the database.** Set this to your existing volume when upgrading a deployment that predates the pinned name — see [Deployment](deployment.md#upgrading-an-existing-deployment). |

The bot service forces:

```text
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

so the container always talks to the Compose `db` service by hostname.

### `DATABASE_URL` precedence

Compose's `environment:` block outranks `env_file:`, and a real environment
variable outranks the `.env` file inside Pydantic Settings. The consequence:

| Launch mode | `DATABASE_URL` in effect |
|---|---|
| `docker compose up` | `…@db:5432/…` from `docker-compose.yml` — the `.env` value is ignored |
| `python -m app.main` on the host | the `.env` value |

These are **different databases** unless the host URL happens to point at the
same Postgres. Pick one launch mode per environment. The value actually in use
is logged at startup (`Database identity: url=…`), so a mismatch is visible in
the first few log lines rather than as missing data.

## Project and volume naming

`docker-compose.yml` pins both:

```yaml
name: vshop                                        # Compose project
volumes:
  pgdata:
    name: ${POSTGRES_VOLUME_NAME:-vshop_pgdata}    # actual Docker volume
```

Without these, Compose derives both from the *directory name*, so deploying the
same code from `/opt/vshop` and `/opt/V-Shop` uses two different databases.

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
