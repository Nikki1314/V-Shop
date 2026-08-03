"""Database session middleware for aiogram handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session_factory

logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Inject an ``AsyncSession`` as ``session`` into handler kwargs.

    Commits on success, rolls back on any exception, always closes the session.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session_factory = get_session_factory()
        session: AsyncSession = session_factory()
        data["session"] = session
        try:
            result = await handler(event, data)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            logger.debug("Database session rolled back after handler error", exc_info=True)
            raise
        finally:
            await session.close()
