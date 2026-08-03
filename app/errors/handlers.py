"""Dispatcher-level error handler (safety net beyond outer middlewares)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from app.errors.classify import log_handled_error
from app.errors.notify import notify_user_of_error, resolve_i18n, safe_user_error_text

logger = logging.getLogger(__name__)


def setup_error_handlers(dispatcher: Dispatcher) -> None:
    """
    Register aiogram ``errors`` handler.

    Covers failures that bypass update outer middlewares (rare), still without
    leaking stack traces to users.
    """

    @dispatcher.errors()
    async def on_error(event: ErrorEvent, bot: Bot, **data: Any) -> bool:
        exc = event.exception
        update = event.update
        user = data.get("event_from_user")
        user_id = getattr(user, "id", None)
        log_handled_error(
            exc,
            update_id=getattr(update, "update_id", None),
            user_id=user_id,
        )
        i18n = resolve_i18n(data)
        text = safe_user_error_text(i18n, exc)
        await notify_user_of_error(update, bot, text)
        # True = error handled; do not re-raise to the polling loop.
        return True

    logger.debug("Dispatcher error handler registered")
