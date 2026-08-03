"""Admin access filter based on ADMIN_IDS from settings."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Settings, get_settings
from app.security.admin import is_admin_user


class IsAdmin(BaseFilter):
    """Allow only Telegram IDs listed in ``ADMIN_IDS``."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def __call__(
        self,
        event: TelegramObject,
        settings: Settings | None = None,
    ) -> bool:
        user = getattr(event, "from_user", None)
        if user is None and isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

        cfg = settings or self._settings or get_settings()
        return is_admin_user(user, cfg)


class IsNotAdmin(BaseFilter):
    """Inverse of :class:`IsAdmin` (used for access-denied replies)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def __call__(
        self,
        event: TelegramObject,
        settings: Settings | None = None,
    ) -> bool:
        admin_filter = IsAdmin(self._settings)
        return not await admin_filter(event, settings=settings)
