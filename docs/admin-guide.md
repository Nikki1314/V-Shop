# Admin guide

Admin features are available only to Telegram user IDs listed in `ADMIN_IDS`.

## Access

1. Ensure your numeric Telegram ID is in `.env` → `ADMIN_IDS`.
2. Restart the bot if you changed env vars.
3. Send `/admin` to the bot.

Authorized users get the admin reply keyboard:

| Button | Section |
|---|---|
| Products | Add / manage catalog products |
| Categories | Create / rename / delete / reorder |
| Orders | View, search, change status |
| Broadcast | Message all registered users |
| Settings | Admin settings entry |

Non-admins who send `/admin` receive an access-denied message and never see admin controls.

While a wizard is active (add product, rename category, broadcast, etc.), tapping another admin menu button is blocked until you **Cancel** or finish the flow.

---

## Products

### Add product

1. **Products** → **Add product**
2. Send a **photo** (required for new products in the wizard)
3. Enter names: RU → EN → DE
4. Enter descriptions: RU → EN → DE
5. Pick a **category** (create categories first if the list is empty)
6. Enter flavor, volume, nicotine strength, price
7. Review the preview → **Confirm**

Prices use decimal format (`12.50`). Scientific notation is rejected.

### Manage products

1. **Products** → **Manage** (paginated list)
2. Open a product card

Actions:

- **Edit** — full edit wizard; **Skip** keeps the current value for a step
- **Edit price** / **Edit description** — focused flows
- **Enable** / **Disable** — catalog visibility (`is_active`)
- **Delete** — confirmation required; blocked if the product appears in any order history

Product images use Telegram `file_id` from the uploaded photo.

---

## Categories

1. Open **Categories**
2. **Create** — enter a unique-enough display name (sorted by `sort_order`)
3. Open a category to:
   - **Rename**
   - **Delete** (blocked if it still has products)
   - **Move up / down** — changes display order in the customer catalog

Create at least one category before adding products.

---

## Orders

1. Open **Orders**
2. View **New** or **Completed** lists (paginated)
3. Open an order for the full card (customer, items, totals, contacts)
4. Change status: **New** → **Accepted** → **Completed**, or **Cancelled**
5. **Search** by order ID, customer name, or phone

New orders also notify:

- `MANAGER_CHAT_ID` (group or private)
- Each ID in `ADMIN_IDS` (private), excluding duplicates

---

## Broadcast

1. Open **Broadcast**
2. Compose **text** and/or send a **photo** (caption optional)
3. Review the preview (recipient count shown)
4. **Confirm** to send

Progress updates appear as the fan-out runs. Soft rate limiting and `RetryAfter` handling reduce Telegram flood errors. Failed recipient IDs are summarized at the end.

Do not double-tap Confirm; the bot serializes broadcast confirms per admin.

---

## Customer-facing reminder

After catalog/product changes:

- Disabled products disappear from the customer catalog
- Category order matches admin reorder
- Cart lines for deleted products are removed (delete only succeeds when not used in orders)

---

## Operational tips

- Keep `ADMIN_IDS` small and trusted — admins can broadcast to every user.
- Use a dedicated manager group for `MANAGER_CHAT_ID` so order alerts are shared.
- If the bot restarts mid-wizard, ask the admin to `/admin` again and restart the flow (FSM is in-memory).
- For TLS interception on a corporate network during local testing only, see `TELEGRAM_SSL_VERIFY` in [Configuration](configuration.md).
