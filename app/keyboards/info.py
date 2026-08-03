"""Information section inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.localization import LocalizationService

CALLBACK_INFO_OPEN = "info:open"
CALLBACK_INFO_DELIVERY = "info:delivery"
CALLBACK_INFO_PAYMENT = "info:payment"
CALLBACK_INFO_CONTACTS = "info:contacts"
CALLBACK_INFO_CHANGE_LANGUAGE = "info:change_language"
CALLBACK_INFO_CHANGE_CITY = "info:change_city"


def info_menu_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    """Main Information actions (city-agnostic labels; content differs by city)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("info.btn_delivery"),
                    callback_data=CALLBACK_INFO_DELIVERY,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("info.btn_payment"),
                    callback_data=CALLBACK_INFO_PAYMENT,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("info.btn_contacts"),
                    callback_data=CALLBACK_INFO_CONTACTS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("info.change_language"),
                    callback_data=CALLBACK_INFO_CHANGE_LANGUAGE,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("info.change_city"),
                    callback_data=CALLBACK_INFO_CHANGE_CITY,
                )
            ],
        ]
    )


def info_back_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("info.back"),
                    callback_data=CALLBACK_INFO_OPEN,
                )
            ]
        ]
    )
