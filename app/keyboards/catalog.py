"""Catalog inline keyboards: Category → Subcategory → Product → Card.

Navigation context is never encoded in callback data. Each level's parent is
derivable from the database (a product knows its brand, a brand knows its
category), so Back needs only the current entity's id. That keeps every payload
far inside Telegram's 64-byte callback limit.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.services.localization import LocalizationService
from app.utils.product_display import localized_category_name, localized_product_name
from app.utils.telegram_ui import truncate_button_label

CALLBACK_CATALOG_OPEN = "catalog:open"
CALLBACK_CATEGORY_PREFIX = "category:"  # -> brands of that category
CALLBACK_SUBCATEGORY_PREFIX = "subcat:"  # -> products of that brand
CALLBACK_PRODUCT_PREFIX = "prod:"  # -> product card


def categories_keyboard(
    categories: list[Category],
    language: str = "en",
) -> InlineKeyboardMarkup:
    """Level 1 — one button per active category."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=truncate_button_label(localized_category_name(category, language)),
                    callback_data=f"{CALLBACK_CATEGORY_PREFIX}{category.id}",
                )
            ]
            for category in categories
        ]
    )


def subcategories_keyboard(
    i18n: LocalizationService,
    subcategories: list[Subcategory],
) -> InlineKeyboardMarkup:
    """Level 2 — brands within a category, plus Back to categories."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=truncate_button_label(localized_category_name(subcategory, i18n.language)),
                callback_data=f"{CALLBACK_SUBCATEGORY_PREFIX}{subcategory.id}",
            )
        ]
        for subcategory in subcategories
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("catalog.back_to_categories"),
                callback_data=CALLBACK_CATALOG_OPEN,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_keyboard(
    i18n: LocalizationService,
    products: list[Product],
    *,
    category_id: int,
) -> InlineKeyboardMarkup:
    """Level 3 — products within a brand, plus Back to brands."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=truncate_button_label(localized_product_name(product, i18n.language)),
                callback_data=f"{CALLBACK_PRODUCT_PREFIX}{product.id}",
            )
        ]
        for product in products
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("catalog.back_to_subcategories"),
                callback_data=f"{CALLBACK_CATEGORY_PREFIX}{category_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_view_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    """Back-only keyboard used when a level has nothing to show."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("catalog.back_to_categories"),
                    callback_data=CALLBACK_CATALOG_OPEN,
                )
            ]
        ]
    )


def subcategory_view_keyboard(
    i18n: LocalizationService,
    category_id: int,
) -> InlineKeyboardMarkup:
    """Back-only keyboard for an empty brand."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("catalog.back_to_subcategories"),
                    callback_data=f"{CALLBACK_CATEGORY_PREFIX}{category_id}",
                )
            ]
        ]
    )
