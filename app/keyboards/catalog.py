"""Catalog inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.category import Category
from app.services.localization import LocalizationService

CALLBACK_CATALOG_OPEN = "catalog:open"
CALLBACK_CATEGORY_PREFIX = "category:"


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """One inline button per category, ordered as provided."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category.name,
                    callback_data=f"{CALLBACK_CATEGORY_PREFIX}{category.id}",
                )
            ]
            for category in categories
        ]
    )


def category_view_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    """Actions available inside an opened category (back only for now)."""
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
