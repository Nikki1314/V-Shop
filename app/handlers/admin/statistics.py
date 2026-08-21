"""Admin statistics dashboard.

Authorization is not repeated here. Three gates upstream already apply to every
update on this router: :class:`PrivateChatMiddleware` drops anything that is not
a private chat, and the admin router adds an :class:`IsAdmin` filter plus
:class:`AdminOnlyMiddleware`. A customer who types the button's text, or anyone
who forwards its callback from a group, never reaches these handlers.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.filters.localized_text import LocalizedText
from app.keyboards.admin_statistics import CALLBACK_STATS_REFRESH, statistics_keyboard
from app.services.localization import LocalizationService
from app.services.statistics import StatisticsService
from app.states.admin import ADMIN_WIZARD_STATES
from app.utils.statistics_display import format_statistics

logger = logging.getLogger(__name__)

router = Router(name="admin_statistics")


async def _render(
    session: AsyncSession,
    i18n: LocalizationService,
    settings: Settings,
) -> str:
    """Collect and format the dashboard in the shop's configured time zone."""
    stats = await StatisticsService(session, settings.app_timezone).collect()
    return format_statistics(stats, i18n, settings.currency_symbol)


@router.message(LocalizedText("admin.menu_statistics"), ~StateFilter(*ADMIN_WIZARD_STATES))
async def open_statistics(
    message: Message,
    session: AsyncSession,
    i18n: LocalizationService,
    settings: Settings,
) -> None:
    await message.answer(
        await _render(session, i18n, settings),
        reply_markup=statistics_keyboard(i18n),
    )


@router.callback_query(F.data == CALLBACK_STATS_REFRESH)
async def refresh_statistics(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
    settings: Settings,
) -> None:
    """Redraw in place. Unchanged figures are a normal outcome, not an error."""
    await callback.answer(i18n.t("admin.stats_refreshed"))
    message = callback.message
    if message is None or not hasattr(message, "edit_text"):
        return
    try:
        await message.edit_text(
            await _render(session, i18n, settings),
            reply_markup=statistics_keyboard(i18n),
        )
    except TelegramBadRequest as exc:
        # Telegram rejects an edit that would not change the message. Nothing has
        # happened in the shop since the last refresh — that is not a failure.
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Statistics unchanged since the last refresh")
