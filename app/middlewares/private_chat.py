"""Private-chat isolation — the single gate for group/supergroup traffic.

Every interactive feature of this bot is one-to-one with a customer or an
administrator, so nothing arriving from a group is ever actionable. This
middleware drops those updates centrally instead of each handler re-checking:
one rule, one place, impossible to forget in a new handler.

It is registered *before* :class:`~app.middlewares.database.DatabaseMiddleware`
on purpose. A dropped update therefore never opens a session, so a group message
cannot touch the database even accidentally — the guarantee is structural rather
than a promise each handler keeps.

Outbound messages are unaffected: manager and review groups still receive order
notifications, because middleware only sees *incoming* updates.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.utils.chat_scope import extract_chat, is_private_chat

logger = logging.getLogger(__name__)

__all__ = ["PrivateChatMiddleware", "extract_chat", "is_private_chat"]


class PrivateChatMiddleware(BaseMiddleware):
    """Drop every update that did not originate in a private chat."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = extract_chat(event)
        if is_private_chat(chat):
            return await handler(event, data)

        user: User | None = data.get("event_from_user")
        logger.debug(
            "Ignoring non-private update: chat_id=%s chat_type=%s user_id=%s",
            getattr(chat, "id", None),
            getattr(chat, "type", None),
            user.id if user is not None else None,
        )
        # Silently. No reply, no session, no state — the group sees nothing.
        return None
