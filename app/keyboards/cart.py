"""Cart inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.cart import CartView
from app.services.localization import LocalizationService

CALLBACK_CART_OPEN = "cart:open"
CALLBACK_CART_INC_PREFIX = "cart:inc:"
CALLBACK_CART_DEC_PREFIX = "cart:dec:"
CALLBACK_CART_RM_PREFIX = "cart:rm:"
CALLBACK_CART_NOOP = "cart:noop"
CALLBACK_CONTINUE_SHOPPING = "catalog:open"
CALLBACK_CHECKOUT = "cart:checkout"


def cart_keyboard(i18n: LocalizationService, view: CartView) -> InlineKeyboardMarkup:
    """
    Per-item controls (➖ / qty / ➕ / remove) plus navigation actions.

    Callback payloads use cart item IDs so quantity changes persist by row.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for line in view.lines:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.t("cart.decrease"),
                    callback_data=f"{CALLBACK_CART_DEC_PREFIX}{line.item_id}",
                ),
                InlineKeyboardButton(
                    text=str(line.quantity),
                    callback_data=CALLBACK_CART_NOOP,
                ),
                InlineKeyboardButton(
                    text=i18n.t("cart.increase"),
                    callback_data=f"{CALLBACK_CART_INC_PREFIX}{line.item_id}",
                ),
                InlineKeyboardButton(
                    text=i18n.t("cart.remove"),
                    callback_data=f"{CALLBACK_CART_RM_PREFIX}{line.item_id}",
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("cart.continue_shopping"),
                callback_data=CALLBACK_CONTINUE_SHOPPING,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("cart.checkout"),
                callback_data=CALLBACK_CHECKOUT,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
