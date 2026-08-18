"""Inline keyboard builders (localized)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.catalog import categories_keyboard, category_view_keyboard
from app.keyboards.product import add_to_cart_keyboard, product_added_keyboard
from app.models.enums import CityChoice, LanguageCode
from app.services.localization import LocalizationService

__all__ = [
    "add_to_cart_keyboard",
    "categories_keyboard",
    "category_view_keyboard",
    "city_keyboard",
    "language_keyboard",
    "product_added_keyboard",
]


def language_keyboard(i18n: LocalizationService | None = None) -> InlineKeyboardMarkup:
    """Language picker. Labels are stable across locales."""
    locator = i18n or LocalizationService.default()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=locator.t("language.ru"),
                    callback_data=f"lang:{LanguageCode.RU.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=locator.t("language.en"),
                    callback_data=f"lang:{LanguageCode.EN.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=locator.t("language.de"),
                    callback_data=f"lang:{LanguageCode.DE.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=locator.t("language.uk"),
                    callback_data=f"lang:{LanguageCode.UK.value}",
                )
            ],
        ]
    )


def city_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("city.berlin"),
                    callback_data=f"city:{CityChoice.BERLIN.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("city.delivery"),
                    callback_data=f"city:{CityChoice.DELIVERY.value}",
                )
            ],
        ]
    )
