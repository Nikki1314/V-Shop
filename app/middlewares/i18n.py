"""Localization middleware — binds language from the database user record."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.localization import LocalizationService

logger = logging.getLogger(__name__)


class LocalizationMiddleware(BaseMiddleware):
    """
    Inject ``i18n`` (:class:`LocalizationService`) and optional ``db_user``.

    Language is taken from ``users.language`` in PostgreSQL when the user exists.
    Falls back to the default locale until the user selects a language.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession | None = data.get("session")
        tg_user: TgUser | None = data.get("event_from_user")

        db_user: User | None = None
        if session is not None and tg_user is not None:
            try:
                db_user = await UserRepository(session).get_by_telegram_id(tg_user.id)
            except Exception:
                logger.exception(
                    "Failed to load db_user for localization telegram_id=%s",
                    tg_user.id,
                )
                # Continue with default locale; do not block the update.
                db_user = None

        data["db_user"] = db_user
        data["i18n"] = LocalizationService.from_user(db_user)
        data["language"] = data["i18n"].language
        return await handler(event, data)
