"""Reviews group access — hands customers an invite link, never a chat ID.

The group is private, so customers must be invited rather than told where it is.
The chat ID is an internal identifier: leaking it lets anyone probe the group
through the Bot API, so it never reaches a user-facing message. Only the invite
link is ever returned from here.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.config import Settings
from app.utils.cache import TtlCache

logger = logging.getLogger(__name__)

# Invite links stay valid until revoked; re-minting one per button press would
# burn API calls and create a new link each time.
_invite_link_cache: TtlCache[str] = TtlCache(ttl_seconds=3600.0)

INVITE_LINK_NAME = "V-Shop reviews"


def invalidate_review_link_cache() -> None:
    """Drop the cached link (configuration change, revoked link, tests)."""
    _invite_link_cache.clear()


class ReviewService:
    """Resolves the customer-facing invite link for the reviews group."""

    def __init__(self, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    @property
    def is_enabled(self) -> bool:
        return self.settings.reviews_enabled

    async def get_invite_link(self) -> str | None:
        """
        Return an invite link, or ``None`` when one cannot be produced.

        Order of preference:

        1. ``REVIEW_INVITE_LINK`` when configured — lets the shop run the
           feature without granting the bot admin rights.
        2. ``createChatInviteLink`` — a named, revocable link.
        3. ``exportChatInviteLink`` — the group's primary link, for bots that
           may invite but not manage links.

        Every Telegram failure is swallowed and logged; callers show a
        localized message rather than an error.
        """
        static_link = self.settings.review_invite_link
        if static_link:
            return static_link

        chat_id = self.settings.review_group_chat_id
        if chat_id is None:
            return None

        cached = _invite_link_cache.get()
        if cached is not None:
            return cached

        link = await self._create_link(chat_id) or await self._export_link(chat_id)
        if link is not None:
            _invite_link_cache.set(link)
        return link

    async def _create_link(self, chat_id: int) -> str | None:
        try:
            invite = await self.bot.create_chat_invite_link(
                chat_id=chat_id,
                name=INVITE_LINK_NAME,
            )
        except TelegramAPIError:
            logger.warning(
                "createChatInviteLink failed for the reviews group; "
                "check the bot is an administrator with can_invite_users",
                exc_info=True,
            )
            return None
        except Exception:
            logger.exception("Unexpected error creating the reviews invite link")
            return None
        return invite.invite_link or None

    async def _export_link(self, chat_id: int) -> str | None:
        try:
            return await self.bot.export_chat_invite_link(chat_id=chat_id)
        except TelegramAPIError:
            logger.warning(
                "exportChatInviteLink also failed for the reviews group",
                exc_info=True,
            )
            return None
        except Exception:
            logger.exception("Unexpected error exporting the reviews invite link")
            return None
