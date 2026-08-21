# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The virtualenv lives at `.venv` (Windows layout: `.venv\Scripts\python.exe`).

```bash
# Setup
pip install -r requirements-dev.txt && pip install -e .

# Run the bot (long polling)
python -m app.main

# Smoke-check wiring + DB + Telegram getMe without entering the polling loop.
# Exit codes: 0 ok, 1 failure, 2 bad/placeholder BOT_TOKEN, 3 Telegram API error.
python -m app.check_startup

# Tests
python -m pytest tests -q
python -m pytest tests/test_admin.py -q                              # one file
python -m pytest tests/test_admin.py::test_admin_category_move -q    # one test

# Lint / types (configured in pyproject.toml; installed via requirements-dev.txt)
ruff check .
mypy app          # strict mode

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1

# Docker (starts Postgres, runs `alembic upgrade head`, then the bot)
docker compose up --build
```

Tests run against in-memory SQLite (`aiosqlite`) — no Postgres needed. `pytest.ini_options` sets `asyncio_mode = "auto"`, so `async def` tests need no decorator (existing tests still carry `@pytest.mark.asyncio`).

Alembic reads `DATABASE_URL` from `app.config.get_settings()` (see `alembic/env.py`) — the `sqlalchemy.url` in `alembic.ini` is a placeholder and is ignored.

## Architecture

Layered aiogram 3 bot; dependencies point inward:

```
Update → outer middlewares → routers → handlers → services → repositories → PostgreSQL
```

Entry: [app/main.py](app/main.py) → [app/bot.py](app/bot.py) (`create_bot` / `create_dispatcher`) → [app/lifecycle.py](app/lifecycle.py) (`on_startup` inits the DB engine, verifies connectivity, drops the webhook, calls `getMe`).

### Handler dependency injection

Handlers receive these keys as named kwargs; the names are fixed by the middleware/dispatcher wiring, not by type:

| Key | Source |
|---|---|
| `session` (`AsyncSession`) | `DatabaseMiddleware` |
| `db_user` (`User \| None`), `i18n` (`LocalizationService`), `language` | `LocalizationMiddleware` |
| `settings` (`Settings`) | `dispatcher["settings"]` workflow data |
| `is_admin` | `AdminOnlyMiddleware` (admin router only) |

Outer middleware order is significant and set in [app/middlewares/__init__.py](app/middlewares/__init__.py): Logging → ErrorHandling → Database → Localization. Errors is *outside* Database so the session has already rolled back before the user-facing message is sent.

### Transactions

`DatabaseMiddleware` commits on handler success and rolls back on any exception, so handlers/services normally only `flush()`. The one deliberate exception is `OrderService.place_order_from_cart`, which commits mid-handler so the order is durable before Telegram notifications go out. It takes a `SELECT … FOR UPDATE` on the cart row (`CartRepository.get_by_user_id_with_items(..., for_update=True)`).

### Router composition

- [app/handlers/user/__init__.py](app/handlers/user/__init__.py) — `start` first (so `/start` wins), then catalog/cart/checkout/info, and `admin_guard` last (the non-admin `/admin` denial must live outside the admin router's filters).
- [app/handlers/admin/__init__.py](app/handlers/admin/__init__.py) — double-gated: router-level `IsAdmin` filters *and* `AdminOnlyMiddleware` (drops unauthorized updates silently). `wizard_guard` is included before the section routers so menu taps mid-FSM are intercepted; `panel` is last.

### Localization

- `app/locales/{en,ru,de,uk}.json`, nested JSON flattened to dotted keys (`menu.catalog`) by [app/utils/i18n.py](app/utils/i18n.py); catalogs are `lru_cache`d.
- Every user-facing string goes through `i18n.t(key, **kwargs)`. Missing keys fall back to English, then return the key itself.
- **All four locale files must have identical key sets** — `test_locales_are_in_sync` fails otherwise. Adding a key means adding it to en/ru/de/uk.
- Reply-keyboard buttons are matched with the `LocalizedText("some.key")` filter, which compares against every language's translation of that key (so a user who switches language mid-session still matches).
- Distinct from locale strings: *product* names/descriptions are per-language **columns** (`name_ru`/`name_en`/`name_de`/`name_uk`, `description_*`) resolved by [app/utils/product_display.py](app/utils/product_display.py).

### Callback data

Namespaced colon-delimited strings declared as `CALLBACK_*` constants in `app/keyboards/*.py` and imported by handlers — never re-typed as literals. Namespaces: `lang:`, `city:`, `catalog:`, `category:`, `cart:`, `checkout:`, `info:`, and admin `admin:product:`, `admin:cat:`, `admin:ord:`, `admin:bc:`. Keep them short — Telegram caps callback data at 64 bytes. Page sizes (`PRODUCTS_PAGE_SIZE`, `ORDERS_PAGE_SIZE`) also live in the keyboard modules, alongside `clamp_page`/`page_count` helpers in [app/utils/telegram_ui.py](app/utils/telegram_ui.py).

### FSM and double-submit protection

`MemoryStorage` — state is process-local, so the bot is single-process by design. Two guards, both required for confirm steps:

- `confirm_once(state, lock_key=...)` ([app/utils/confirm.py](app/utils/confirm.py)) — yields FSM data only on the first submission, `None` afterwards; resets `submitted` on exception so the user can retry.
- `keyed_lock(key)` ([app/utils/concurrency.py](app/utils/concurrency.py)) — process-local async lock (checkout uses it directly; admin wizards get it through `confirm_once`).

State groups are in `app/states/`. `ADMIN_WIZARD_STATES` aggregates every admin wizard group and drives the wizard guard — a new admin wizard must be registered there or menu taps will corrupt its state.

### Services and repositories

`BaseRepository` ([app/repositories/base.py](app/repositories/base.py)) provides generic CRUD; per-aggregate repos add queries. `AdminService` is a backwards-compatible façade over `AdminCatalogService` / `AdminOrderService` / `AdminUserService` — prefer the focused services in new code.

### Errors

[app/errors/classify.py](app/errors/classify.py) maps exceptions to `telegram` / `database` / `network` / `unexpected` and to a locale key (`error.*`). Users only ever see the localized generic message; stack traces stay in logs. A dispatcher-level `errors` handler is the final safety net.

### Caching

Category lists use a 60s process-local TTL cache ([app/utils/cache.py](app/utils/cache.py)). Any category mutation must call `invalidate_categories_cache()` — tests that touch categories clear it in an autouse fixture.

## Conventions

- Parse mode is HTML globally (`DefaultBotProperties`). Interpolate any user- or DB-supplied value through `e()` from [app/utils/html.py](app/utils/html.py).
- Enums are `StrEnum` persisted **by value** (`native_enum=False` + `enum_values()` from [app/models/types.py](app/models/types.py)) — `ru`, `berlin`, `New`, not `RU`/`BERLIN`/`NEW`.
- `Decimal` for money end to end (`Numeric(10,2)`); never floats.
- Delivery options are city-gated: Berlin → `pickup`/`courier`, other cities → `postal`/`service` (`delivery_allowed_for_city` in [app/services/order.py](app/services/order.py)); enforce it server-side, not only in the keyboard.
- FK integrity intentionally blocks deletes: a category with products, and a product referenced by `order_items`, cannot be deleted (`ON DELETE RESTRICT` → `CategoryInUseError` / `ProductInUseError`).
- New ORM models must be exported from [app/models/__init__.py](app/models/__init__.py) and imported in `alembic/env.py`, or autogenerate will miss them.
- `ADMIN_IDS` fail-closes: empty means nobody has admin access. It accepts `1,2`, `[1, 2]`, or a single int.
- Extended docs live in [docs/](docs/) (architecture, database schema, configuration, deployment, admin guide) and are kept current — update them alongside structural changes.
