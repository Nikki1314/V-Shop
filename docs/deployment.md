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

## Upgrading an existing deployment

**Do this once, before the first deploy of a version that pins the volume name.**

Earlier revisions of `docker-compose.yml` did not pin the Compose project or the
volume name, so both were derived from the deployment directory. Your database
may therefore live in a volume named after that directory (`v-shop_pgdata`,
`vshop-2026_pgdata`, …) rather than the new default `vshop_pgdata`. Deploying
without checking would start the stack against a **new, empty** database.

1. Find the volume currently in use:

```bash
docker inspect vshop-db --format '{{ (index .Mounts 0).Name }}'
docker volume ls
```

2. If the name is **not** `vshop_pgdata`, record it in `.env`:

```env
POSTGRES_VOLUME_NAME=v-shop_pgdata
```

3. Take a backup (see below) and note the cluster identity:

```bash
docker exec vshop-db psql -U vshop -d vshop -tAc \
  "SELECT system_identifier FROM pg_control_system();"
```

4. Stop the old stack **from its original directory** so the pinned
   `container_name` values are released, then deploy normally:

```bash
docker compose down          # in the OLD directory
docker compose up -d --build # in the new one
```

If you forget step 4 the deploy fails loudly with a container-name conflict —
that is intentional, and preferable to starting a second stack silently.

5. Confirm the data came with you (see *Verifying a deploy* below).

### Updates

```bash
git pull
docker compose up -d --build
```

The bot entrypoint always runs `alembic upgrade head` before polling, so schema migrations apply on deploy.

Because the project and volume names are pinned in `docker-compose.yml`, this is
safe to run from any directory — the stack always attaches to the same database.

### Verifying a deploy

Every startup logs which database it attached to:

```text
Database identity: url=postgresql+asyncpg://vshop:***@db:5432/vshop
  system_identifier=7675364240903147554 categories=12 products=84 users=430 orders=1180
```

Check two things in that line:

- **`system_identifier` is unchanged from the previous deploy.** It is assigned
  once at `initdb` and uniquely identifies a PostgreSQL cluster. A new value
  means the stack is attached to different storage — the connection string,
  database name and OID all stay identical in that case, so this is the only
  cheap way to notice.
- **The row counts match what you expect.** An unexpectedly empty catalog also
  raises an explicit `WARNING` on the next line.

If either looks wrong, **stop and investigate before adding any data** — the
original volume is very likely still on disk and recoverable (`docker volume ls`).

## Safe operations

These preserve all production data and are the only commands needed for routine
operation.

```bash
docker compose up -d --build   # deploy / update
docker compose restart bot     # restart the app only
docker compose down            # stop the stack; the database volume is KEPT
docker compose logs -f bot     # follow logs
docker compose ps              # status
```

## Backups

There is no automatic backup. Take one before every deploy and before any schema
change:

```bash
docker exec vshop-db pg_dump -U vshop -Fc vshop > vshop-$(date +%F).dump
```

Verify the dump restores before trusting it — an untested dump is not a backup:

```bash
docker exec -i vshop-db createdb -U vshop restore_check
docker exec -i vshop-db pg_restore -U vshop -d restore_check < vshop-YYYY-MM-DD.dump
docker exec vshop-db psql -U vshop -d restore_check -c "SELECT count(*) FROM products;"
docker exec vshop-db dropdb -U vshop restore_check
```

## Destructive operations

> **Never run these as part of a normal update.** Each one permanently deletes
> production data. Take and verify a backup first, and only run them when a
> complete environment reset is explicitly intended.

| Command | Effect |
|---|---|
| `docker compose down -v` | **Deletes the database volume.** All users, catalog, carts and order history are gone. |
| `docker volume rm <name>` | Same, targeted at one volume. |
| `docker volume prune` | Deletes **every** unreferenced volume on the host. `docker compose down` leaves the database volume unreferenced, so this destroys it. |
| `docker system prune -a --volumes` | As above, plus images. |
| `alembic downgrade …` | Drops tables. Never run against production. |

Because `docker compose down` leaves `pgdata` dangling, do not schedule any
Docker cleanup job on this host. If disk reclamation is genuinely needed, scope
it — `docker image prune` is safe; volume pruning is not.

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
- [ ] `POSTGRES_VOLUME_NAME` matches the volume that actually holds your data
- [ ] `system_identifier` recorded, so it can be compared after each deploy
- [ ] No `docker volume prune` / `docker system prune --volumes` in any cron or cleanup job
- [ ] Backups scheduled **and a restore tested**
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
3. Logs the database identity (URL, `system_identifier`, row counts) — read-only
4. Creates the bot/dispatcher
5. Calls Telegram `getMe` (startup check)
6. Begins long polling

Step 3 never writes and never blocks startup: if the probe fails it is logged at
`DEBUG` and the bot continues.

If DB or token checks fail, the process exits non-zero (Compose will restart if `restart: unless-stopped`).

## Reverse proxy / webhooks

The bot uses **long polling**, not webhooks. No inbound HTTP port is required for Telegram. If you later switch to webhooks, you would need a public HTTPS endpoint and webhook secret handling (not implemented in this repo).
