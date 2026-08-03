# Deployment

## Recommended: Docker Compose

The repository ships a production-oriented Compose stack:

| Service | Role |
|---|---|
| `db` | PostgreSQL 16 Alpine, named volume `pgdata`, healthcheck |
| `bot` | App image; migrates then runs `python -m app.main` |

### Deploy steps

1. Provision a host with Docker and Docker Compose.
2. Copy the project (or pull from git).
3. Create `.env` with **production** secrets (strong DB password, real `BOT_TOKEN`, locked-down `ADMIN_IDS`).
4. Postgres is published on `127.0.0.1` only by default (see `docker-compose.yml`). For stricter production, omit the `db` ports mapping entirely so only the bot container can reach Postgres on the internal network.
5. Start:

```bash
docker compose up -d --build
```

6. Follow logs:

```bash
docker compose logs -f bot
```

### Updates

```bash
git pull
docker compose up -d --build
```

The bot entrypoint always runs `alembic upgrade head` before polling, so schema migrations apply on deploy.

### Stop / backup

```bash
docker compose down          # keeps pgdata volume
docker compose down -v       # destroys database volume — irreversible
```

Backup the `pgdata` volume or use `pg_dump` against Postgres before major upgrades.

## Image build

`Dockerfile` uses `python:3.13-slim`, installs `requirements.txt`, copies `app/` + Alembic, then `pip install -e .`.

Default command: `python -m app.main` (Compose overrides with migrate + main).

## Production checklist

- [ ] Real `BOT_TOKEN` (never the `.env.example` placeholder)
- [ ] Strong `POSTGRES_PASSWORD` / credentials in `DATABASE_URL`
- [ ] `ADMIN_IDS` limited to trusted operators
- [ ] `MANAGER_CHAT_ID` points at the correct ops chat
- [ ] `TELEGRAM_SSL_VERIFY=true`
- [ ] `APP_ENV=production` and `LOG_LEVEL=INFO` (or `WARNING`)
- [ ] Postgres not exposed publicly
- [ ] Host firewall / reverse proxy as needed (bot uses outbound HTTPS to Telegram only)
- [ ] Volume backups scheduled
- [ ] Single bot instance per token (MemoryStorage FSM is process-local; multiple replicas need Redis FSM storage first)

## Scaling notes

Current defaults suit a **single** bot process:

- FSM uses `MemoryStorage` (lost on restart; not shared across workers).
- Category list uses a process-local TTL cache.
- Checkout/broadcast anti-double-submit uses in-process locks **plus** Postgres cart `FOR UPDATE` for orders.

For multiple workers, introduce Redis (or similar) FSM storage and shared locking before scaling out.

## Health expectations

On startup the app:

1. Configures logging
2. Initializes the DB engine and checks `SELECT 1`
3. Creates the bot/dispatcher
4. Calls Telegram `getMe` (startup check)
5. Begins long polling

If DB or token checks fail, the process exits non-zero (Compose will restart if `restart: unless-stopped`).

## Reverse proxy / webhooks

The bot uses **long polling**, not webhooks. No inbound HTTP port is required for Telegram. If you later switch to webhooks, you would need a public HTTPS endpoint and webhook secret handling (not implemented in this repo).
