"""Request logging middleware for Telegram updates."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

logger = logging.getLogger(__name__)


def _update_kind(update: Update) -> str:
    for name in (
        "message",
        "edited_message",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "poll",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        if getattr(update, name, None) is not None:
            return name
    return "unknown"


def _user_from_update(update: Update) -> User | None:
    for attr in (
        "message",
        "edited_message",
        "callback_query",
        "inline_query",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ):
        event = getattr(update, attr, None)
        if event is None:
            continue
        user = getattr(event, "from_user", None)
        if isinstance(user, User):
            return user
    return None


class LoggingMiddleware(BaseMiddleware):
    """
    Log each update with user id, type, and handling duration.

    Registered as the outermost middleware so timing covers the full pipeline.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update_id = getattr(event, "update_id", None)
        kind = _update_kind(event) if isinstance(event, Update) else type(event).__name__
        user = data.get("event_from_user")
        if user is None and isinstance(event, Update):
            user = _user_from_update(event)
        user_id = user.id if isinstance(user, User) else None

        logger.info(
            "Update received update_id=%s kind=%s user_id=%s",
            update_id,
            kind,
            user_id,
        )
        started = time.perf_counter()
        try:
            result = await handler(event, data)
        except Exception:
            elapsed = time.perf_counter() - started
            logger.exception(
                "Update failed update_id=%s kind=%s user_id=%s elapsed=%.3fs",
                update_id,
                kind,
                user_id,
                elapsed,
            )
            raise

        elapsed = time.perf_counter() - started
        logger.info(
            "Update handled update_id=%s kind=%s user_id=%s elapsed=%.3fs",
            update_id,
            kind,
            user_id,
            elapsed,
        )
        return result
