"""Product-related inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.cart import CALLBACK_CART_OPEN, CALLBACK_CONTINUE_SHOPPING
from app.services.localization import LocalizationService

CALLBACK_CART_ADD_PREFIX = "cart:add:"


def add_to_cart_keyboard(
    i18n: LocalizationService,
    product_id: int,
    *,
    subcategory_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Product card actions. ``subcategory_id`` adds Back to that brand."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.t("product.add_to_cart"),
                callback_data=f"{CALLBACK_CART_ADD_PREFIX}{product_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.t("product.open_cart"),
                callback_data=CALLBACK_CART_OPEN,
            )
        ],
    ]
    if subcategory_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.t("product.back"),
                    callback_data=f"subcat:{subcategory_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_added_keyboard(
    i18n: LocalizationService,
    *,
    subcategory_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Shown after adding to the cart.

    ``subcategory_id`` keeps the customer where they were: "continue shopping"
    returns to that brand's product list instead of the top of the catalog.
    Without it (legacy products carrying no brand) it falls back to categories.
    """
    continue_target = (
        f"subcat:{subcategory_id}"
        if subcategory_id is not None
        else CALLBACK_CONTINUE_SHOPPING
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("product.continue_shopping"),
                    callback_data=continue_target,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("product.open_cart"),
                    callback_data=CALLBACK_CART_OPEN,
                )
            ],
        ]
    )
