"""Best-effort user notifications for handled errors (no stack traces)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.errors.classify import locale_key_for_error
from app.services.localization import LocalizationService
from app.utils.chat_scope import is_private_event

logger = logging.getLogger(__name__)


def resolve_i18n(data: dict[str, Any]) -> LocalizationService:
    i18n = data.get("i18n")
    if isinstance(i18n, LocalizationService):
        return i18n
    return LocalizationService()


def safe_user_error_text(i18n: LocalizationService, exc: BaseException) -> str:
    """
    Build a localized user message.

    Never interpolates ``str(exc)`` or traceback content.
    """
    return i18n.t(locale_key_for_error(exc))


async def notify_user_of_error(
    event: TelegramObject,
    bot: Bot | None,
    text: str,
) -> None:
    """
    Deliver a short safe message; swallow notification failures.

    Refuses non-private chats. This runs on paths that can fire *before* the
    private-chat middleware — aiogram's own error handling, and any failure in
    an earlier middleware — so without this check a group could be answered by
    the bot purely because something threw.
    """
    if not is_private_event(event):
        logger.debug("Suppressing error notification for a non-private chat")
        return

    try:
        if isinstance(event, Update):
            if event.callback_query is not None:
                await _notify_callback(event.callback_query, bot, text)
                return
            message = event.message or event.edited_message
            if message is not None:
                await message.answer(text)
            return

        if isinstance(event, CallbackQuery):
            await _notify_callback(event, bot, text)
            return

        if isinstance(event, Message):
            await event.answer(text)
    except Exception:
        logger.debug("Could not notify user about handled error", exc_info=True)


async def _notify_callback(
    callback: CallbackQuery,
    bot: Bot | None,
    text: str,
) -> None:
    try:
        await callback.answer(text[:200], show_alert=True)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramAPIError):
        logger.debug("Could not answer error callback", exc_info=True)

    message = callback.message
    if isinstance(message, Message) and is_private_event(message):
        try:
            await message.answer(text)
            return
        except Exception:
            logger.debug("Could not send error via callback.message", exc_info=True)

    if bot is not None and callback.from_user is not None:
        try:
            await bot.send_message(callback.from_user.id, text)
        except Exception:
            logger.debug("Could not DM user after error callback failure", exc_info=True)
