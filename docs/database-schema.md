# Database schema

PostgreSQL schema is managed by Alembic.

| Revision | Purpose |
|---|---|
| `a9b389353e68` | Initial tables |
| `b2c4d5e6f7a8` | Performance indexes |

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
                     products *──1 categories
```

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
| `name` | varchar(255) | Display name |
| `sort_order` | int | Default `0`; lower sorts first |

Indexes: `sort_order`, `name`.

### `products`

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `category_id` | int FK → categories | `ON DELETE RESTRICT` |
| `name_ru` / `name_en` / `name_de` | varchar(255) | Localized names |
| `description_ru` / `en` / `de` | text | Localized descriptions |
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
