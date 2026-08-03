"""Application startup and shutdown hooks (aiogram 3 lifecycle)."""

from __future__ import annotations

import logging

from aiogram import Bot

from app.config import Settings
from app.database.session import check_db_connection, close_db, init_db

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, settings: Settings) -> None:
    """
    Run once before polling begins.

    - Initialize DB engine / session factory
    - Verify PostgreSQL connectivity
    - Drop webhook (long-polling mode)
    - Confirm Telegram authorization via getMe
    """
    logger.info("Startup: initializing infrastructure (env=%s)", settings.app_env)

    await init_db()
    await check_db_connection()

    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logger.info(
        "Startup complete: bot=@%s id=%s can_join_groups=%s",
        me.username,
        me.id,
        me.can_join_groups,
    )


async def on_shutdown() -> None:
    """Run once when the dispatcher stops (Ctrl+C / process exit)."""
    logger.info("Shutdown: releasing resources")
    await close_db()
    logger.info("Shutdown complete")
