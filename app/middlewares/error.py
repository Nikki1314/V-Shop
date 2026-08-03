"""Global error-handling middleware — never expose stack traces to users."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update, User

from app.errors.classify import log_handled_error
from app.errors.notify import notify_user_of_error, resolve_i18n, safe_user_error_text


def _update_id(event: TelegramObject) -> int | None:
    return getattr(event, "update_id", None) if isinstance(event, Update) else None


def _user_id(data: dict[str, Any]) -> int | None:
    user = data.get("event_from_user")
    return user.id if isinstance(user, User) else None


class ErrorHandlingMiddleware(BaseMiddleware):
    """
    Catch unhandled exceptions from the inner pipeline.

    Placed outside :class:`DatabaseMiddleware` so failed handlers roll back,
    then this middleware notifies the user with a safe localized message and
    swallows the error (keeps polling alive).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            log_handled_error(
                exc,
                update_id=_update_id(event),
                user_id=_user_id(data),
            )
            i18n = resolve_i18n(data)
            text = safe_user_error_text(i18n, exc)
            bot: Bot | None = data.get("bot")
            await notify_user_of_error(event, bot, text)
            return None
