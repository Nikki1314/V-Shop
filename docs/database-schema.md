# Database schema

PostgreSQL schema is managed by Alembic.

| Revision | Purpose |
|---|---|
| `a9b389353e68` | Initial tables |
| `b2c4d5e6f7a8` | Performance indexes |
| `c7e1f4a9d3b6` | Catalog hierarchy: `subcategories`, localized names, `uk` columns |

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1
```

## Entity relationship

```text
users 1──1 carts 1──* cart_items *──1 products
  │                              ▲
  │                              │
  └──* orders 1──* order_items ──┘

categories 1──* subcategories 1──* products      ← current hierarchy
categories 1──────────────────* products         ← legacy link, retained
```

## Catalog hierarchy

`Category → Subcategory → Product`. Both levels carry four localized names
(`ru` / `en` / `de` / `uk`), `sort_order`, `is_active` and timestamps.

Two columns are **deliberately retained** from the pre-hierarchy schema so the
existing handlers keep working while the catalog UI is migrated:

| Legacy column | Superseded by | Status |
|---|---|---|
| `categories.name` | `categories.name_{ru,en,de,uk}` | Still written, kept in sync by `CategoryRepository` |
| `products.category_id` | `products.subcategory_id` | Still written; `subcategory_id` is nullable until product creation collects one |

A later **contract** migration drops both once the catalog and admin UI read the
hierarchy. Until then `alembic check` stays clean because the models still map
them.

## Tables

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | Internal ID |
| `telegram_id` | bigint | Unique, indexed |
| `username` | varchar(255) | Nullable |
| `first_name` | varchar(255) | Nullable |
| `language` | varchar(8) | `ru` / `en` / `de`, nullable until onboarding |
| `selected_city` | varchar(32) | `berlin` / `delivery`, nullable until onboarding |
| `last_seen` | timestamptz | Default `now()` |
| `created_at` | timestamptz | Default `now()` |

### `categories`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `name` | varchar(255) | **Legacy** single-language name; kept in sync on write |
| `name_ru` / `name_en` / `name_de` / `name_uk` | varchar(255) | Localized names |
| `sort_order` | int | Default `0`; lower sorts first |
| `is_active` | boolean | Default `true` |
| `created_at` / `updated_at` | timestamptz | `updated_at` maintained on write |

Indexes: `sort_order`, `name`, `is_active`.

### `subcategories`

Brand / product group inside a category.

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `category_id` | int FK → categories | `ON DELETE RESTRICT` |
| `name_ru` / `name_en` / `name_de` / `name_uk` | varchar(255) | Localized names |
| `sort_order` | int | Default `0` |
| `is_active` | boolean | Default `true` |
| `created_at` / `updated_at` | timestamptz | |

Indexes: `category_id`, composite `(category_id, is_active)`, `sort_order`.

### `products`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `subcategory_id` | int FK → subcategories, nullable | `ON DELETE RESTRICT`; the hierarchy link |
| `category_id` | int FK → categories | **Legacy** direct link, `ON DELETE RESTRICT` |
| `name_ru` / `name_en` / `name_de` / `name_uk` | varchar(255) | Localized names |
| `description_ru` / `en` / `de` / `uk` | text | Localized descriptions |
| `updated_at` | timestamptz | Maintained on write |
| `flavor` | varchar(255) | |
| `volume` | varchar(64) | |
| `nicotine_strength` | varchar(64) | |
| `price` | numeric(10,2) | |
| `image_file_id` | varchar(255) | Telegram file_id, nullable |
| `is_active` | boolean | Default `true` |
| `created_at` | timestamptz | |

Indexes: `category_id`, composite `(category_id, is_active)`.

### `carts`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `user_id` | int FK → users | Unique; `ON DELETE CASCADE` |

### `cart_items`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `cart_id` | int FK → carts | `ON DELETE CASCADE` |
| `product_id` | int FK → products | `ON DELETE CASCADE` |
| `quantity` | int | `> 0`; default `1` |

Unique `(cart_id, product_id)`.

### `orders`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `user_id` | int FK → users | `ON DELETE RESTRICT` |
| `customer_name` | varchar(255) | |
| `city` | varchar(32) | Snapshot of city choice |
| `delivery_type` | varchar(64) | `pickup` / `courier` / `postal` / `service` |
| `address` | text | |
| `preferred_time` | varchar(255) | Nullable |
| `phone` | varchar(64) | Nullable (Telegram contact path) |
| `total_price` | numeric(10,2) | `>= 0` |
| `status` | varchar(32) | `New` / `Accepted` / `Completed` / `Cancelled` |
| `created_at` | timestamptz | |

Indexes: `user_id`, `status`, composite `(status, created_at)`.

### `order_items`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `order_id` | int FK → orders | `ON DELETE CASCADE` |
| `product_id` | int FK → products | `ON DELETE RESTRICT` (blocks product delete if used) |
| `quantity` | int | `> 0` |
| `price` | numeric(10,2) | Unit price snapshot; `>= 0` |

## Status & enum values

Stored as string enums (`native_enum=False`):

- **Language**: `ru`, `en`, `de`
- **City**: `berlin`, `delivery`
- **Order status**: `New`, `Accepted`, `Completed`, `Cancelled`

## Integrity rules (application + DB)

- Cannot delete a **category** that still has products.
- Cannot delete a **product** referenced by `order_items`.
- Cart lines cascade when a product is deleted (if not blocked by orders).
- Checkout clears `cart_items` after creating the order in the same transaction.

## ORM location

Models live under `app/models/`. Repositories under `app/repositories/`.
