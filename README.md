# V-Shop

Telegram shop bot for a vape e-liquid store.

Customers browse a multilingual catalog, manage a cart, and check out through a guided FSM. Admins manage products, categories, orders, and broadcasts from Telegram.

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.13 |
| Bot | aiogram 3.x (long polling) |
| ORM | SQLAlchemy 2.x async + asyncpg |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Config | Pydantic Settings |
| Deploy | Docker / Docker Compose |

## Features

**Customer**
- Onboarding: language (EN / RU / DE) → city (Berlin / other cities)
- Catalog by category with product cards and add-to-cart
- Cart quantity controls and checkout FSM
- Order confirmation + manager/admin notifications

**Admin** (`/admin`, `ADMIN_IDS` only)
- Products: add, list, edit, price/description, enable/disable, delete
- Categories: create, rename, delete, reorder
- Orders: new/completed lists, search, status changes
- Broadcast: text and/or photo to all registered users

## Documentation

| Guide | Description |
|---|---|
| [Installation](docs/installation.md) | Local and Docker setup |
| [Configuration](docs/configuration.md) | Environment variables |
| [Deployment](docs/deployment.md) | Production Docker notes |
| [Architecture](docs/architecture.md) | Layers, middleware, flows |
| [Database schema](docs/database-schema.md) | Tables, indexes, relations |
| [Admin guide](docs/admin-guide.md) | Operating the admin panel |

## Quick start

```bash
cp .env.example .env
# Set BOT_TOKEN, ADMIN_IDS, MANAGER_CHAT_ID

docker compose up --build
```

Compose starts PostgreSQL, runs `alembic upgrade head`, then launches the bot.

## Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
# Point DATABASE_URL at local Postgres

alembic upgrade head
python -m app.main
```

Run tests:

```bash
python -m pytest tests -q
```

## Project layout

```
app/
  handlers/        # Telegram routers (user / admin)
  keyboards/       # Reply & inline keyboards
  middlewares/     # Logging, errors, DB session, i18n
  services/        # Business orchestration
  repositories/    # Data access
  models/          # SQLAlchemy ORM
  states/          # FSM groups
  locales/         # en / ru / de JSON
  utils/           # Validators, labels, cache, …
  errors/          # Error classification & safe user text
docs/              # Extended documentation
tests/             # pytest suite (async SQLite)
```

## License

Proprietary.
