"""Admin broadcast keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.localization import LocalizationService

CALLBACK_BROADCAST_START = "admin:bc:start"
CALLBACK_BROADCAST_CONFIRM = "admin:bc:confirm"
CALLBACK_BROADCAST_CANCEL = "admin:bc:cancel"


def broadcast_actions_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.broadcast_start"),
                    callback_data=CALLBACK_BROADCAST_START,
                )
            ]
        ]
    )


def broadcast_confirm_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.broadcast_confirm"),
                    callback_data=CALLBACK_BROADCAST_CONFIRM,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("common.cancel"),
                    callback_data=CALLBACK_BROADCAST_CANCEL,
                )
            ],
        ]
    )
