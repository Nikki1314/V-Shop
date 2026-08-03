# Architecture

## Overview

V-Shop is a layered Telegram bot:

```text
Telegram update
    → Middlewares (log → errors → DB session → i18n)
    → Routers (user | admin)
    → Handlers
    → Services
    → Repositories
    → PostgreSQL
```

Dependencies point inward. Handlers do not talk to SQLAlchemy sessions for business rules beyond injecting `session` into services/repositories.

## Package map

| Package | Responsibility |
|---|---|
| `app/handlers/` | Aiogram routers: parse updates, drive FSM, call services |
| `app/keyboards/` | Reply / inline keyboard builders + callback prefixes |
| `app/middlewares/` | Cross-cutting: logging, errors, session lifecycle, localization |
| `app/filters/` | `IsAdmin`, `LocalizedText` (menu button matching) |
| `app/services/` | Use-cases: cart, catalog, order, admin façade, broadcast, notifications |
| `app/repositories/` | CRUD and query helpers per aggregate |
| `app/models/` | SQLAlchemy ORM + domain enums |
| `app/states/` | FSM `StatesGroup` definitions |
| `app/locales/` | Nested JSON catalogs (flattened to dotted keys) |
| `app/utils/` | Validators, labels, cache, concurrency, Telegram UI helpers |
| `app/errors/` | Classify exceptions → safe localized user messages |
| `app/security/` | Admin ID checks |
| `app/config.py` | Settings |
| `app/bot.py` | Bot + dispatcher factory |
| `app/main.py` | Process entrypoint |

## Middleware order

Registered as outer update middlewares (first = outermost):

1. **Logging** — timing / request log
2. **Error handling** — catch handler failures, answer with safe text
3. **Database** — open `AsyncSession`, commit on success, rollback on error, close
4. **Localization** — load `db_user`, inject `i18n` / `language`

Dispatcher-level `errors` handlers act as a final safety net.

## Routing

```text
root
 ├── user router
│   ├── /start onboarding
│   ├── catalog / cart / checkout
│   ├── information
│   └── /admin access-denied for non-admins
└── admin router  (IsAdmin filter + AdminOnlyMiddleware)
    ├── wizard guard (block menu jumps mid-FSM)
    ├── products (add wizard)
    ├── product_manage (list / edit / delete)
    ├── categories
    ├── orders
    ├── broadcast
    ├── settings
    └── panel (/admin menu)
```

## Main user flows

### Onboarding

`/start` → ensure user row → choose language → choose city → main reply keyboard (Catalog / Cart / Info).

### Catalog → cart

Catalog → categories → product cards → add to cart → cart (± quantity, remove) → checkout.

### Checkout (FSM)

Name → delivery type (city-dependent) → address → preferred time → phone (contact share or typed) → confirmation → `OrderService.place_order_from_cart` → notify `MANAGER_CHAT_ID` + `ADMIN_IDS`.

Cart row is locked with `SELECT … FOR UPDATE` during placement; FSM `submitted` + process lock reduce double-taps.

## Admin services (SOLID split)

`AdminService` is a façade over:

- `AdminCatalogService` — categories & products
- `AdminOrderService` — order queries & status
- `AdminUserService` — broadcast recipient IDs

Handlers may use the façade or focused services.

## Localization

- Files: `app/locales/{en,ru,de}.json`
- Keys flattened to dotted paths (`menu.catalog`)
- `LocalizationService.t(key, **kwargs)` formats strings
- Menu buttons matched via `LocalizedText` against all language variants

## Concurrency & caching

- Process-local `keyed_lock` for confirm actions (checkout, broadcast, product create/edit)
- Category list TTL cache (`app/utils/cache.py`), invalidated on category mutations
- FSM: `MemoryStorage` (single process)

## Error UX

Exceptions are classified (`telegram` / `database` / `network` / `unexpected`). Users only see localized generic messages — never stack traces or raw DB errors.

## Testing

`tests/` uses pytest-asyncio and in-memory SQLite. Factories seed users/products/orders. See `tests/conftest.py`.
