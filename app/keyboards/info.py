"""Information section inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.localization import LocalizationService

CALLBACK_INFO_OPEN = "info:open"
CALLBACK_INFO_DELIVERY = "info:delivery"
CALLBACK_INFO_PAYMENT = "info:payment"
CALLBACK_INFO_CONTACTS = "info:contacts"
CALLBACK_INFO_REVIEWS = "info:reviews"
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
                    text=i18n.t("info.btn_reviews"),
                    callback_data=CALLBACK_INFO_REVIEWS,
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


def info_back_keyboard(
    i18n: LocalizationService,
    *,
    with_reviews: bool = False,
) -> InlineKeyboardMarkup:
    """Back to the Information menu.

    ``with_reviews`` adds a Reviews shortcut, used on the Contacts screen: that
    text tells customers to ask in the group, so the way there should be one tap
    away rather than a trip back through the menu.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if with_reviews:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.t("info.btn_reviews"),
                    callback_data=CALLBACK_INFO_REVIEWS,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("info.back"),
                callback_data=CALLBACK_INFO_OPEN,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reviews_keyboard(i18n: LocalizationService, invite_link: str) -> InlineKeyboardMarkup:
    """A URL button carrying only the invite link — never the chat ID."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("info.reviews_open"),
                    url=invite_link,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("info.back"),
                    callback_data=CALLBACK_INFO_OPEN,
                )
            ],
        ]
    )
