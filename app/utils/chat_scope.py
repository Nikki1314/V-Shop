"""Where an update came from, and whether the bot may talk back there.

Shared by the private-chat middleware (which drops group traffic) and the error
notifier (which must not answer into a group even when something failed before
the middleware ran). Keeping the rule in one place means the two cannot drift.
"""

from __future__ import annotations

from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update

# Update fields that carry a chat we can judge.
CHAT_BEARING_FIELDS = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "message_reaction",
    "message_reaction_count",
)


def extract_chat(event: TelegramObject) -> Chat | None:
    """
    Best-effort chat for an update, or ``None`` when it has none.

    ``None`` means *undeterminable*, not *allowed*: callers must fail closed.
    Business-account updates are deliberately absent from the field list — the
    bot serves no business features, so those drop rather than being judged.
    """
    if isinstance(event, Update):
        callback = event.callback_query
        if callback is not None:
            # Works for Message and InaccessibleMessage alike; None for
            # inline-mode callbacks, which this bot does not serve.
            origin = getattr(callback.message, "chat", None)
            return origin if isinstance(origin, Chat) else None

        for field in CHAT_BEARING_FIELDS:
            carrier = getattr(event, field, None)
            if carrier is None:
                continue
            chat = getattr(carrier, "chat", None)
            if isinstance(chat, Chat):
                return chat
        return None

    if isinstance(event, CallbackQuery):
        origin = getattr(event.message, "chat", None)
        return origin if isinstance(origin, Chat) else None

    if isinstance(event, Message):
        return event.chat

    direct = getattr(event, "chat", None)
    return direct if isinstance(direct, Chat) else None


def is_private_chat(chat: Chat | None) -> bool:
    return chat is not None and chat.type == ChatType.PRIVATE


def is_private_event(event: TelegramObject) -> bool:
    """Whether the bot may interact with the origin of ``event``."""
    return is_private_chat(extract_chat(event))
