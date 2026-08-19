"""Inline keyboard for the statistics dashboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.localization import LocalizationService

CALLBACK_STATS_REFRESH = "admin:st:rf"


def statistics_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    """A single Refresh button — a dashboard is stale the moment it is drawn."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.stats_refresh"),
                    callback_data=CALLBACK_STATS_REFRESH,
                )
            ]
        ]
    )
