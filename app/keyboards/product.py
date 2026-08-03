"""Product-related inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.cart import CALLBACK_CART_OPEN, CALLBACK_CONTINUE_SHOPPING
from app.services.localization import LocalizationService

CALLBACK_CART_ADD_PREFIX = "cart:add:"


def add_to_cart_keyboard(i18n: LocalizationService, product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("product.add_to_cart"),
                    callback_data=f"{CALLBACK_CART_ADD_PREFIX}{product_id}",
                )
            ]
        ]
    )


def product_added_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("product.continue_shopping"),
                    callback_data=CALLBACK_CONTINUE_SHOPPING,
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
