"""Bot and dispatcher factory (aiogram 3)."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import Settings
from app.handlers import setup_routers
from app.lifecycle import on_shutdown, on_startup
from app.middlewares import setup_middlewares

logger = logging.getLogger(__name__)


def _build_session(settings: Settings) -> AiohttpSession:
    """Create the HTTP session, honoring TELEGRAM_SSL_VERIFY."""
    session = AiohttpSession()
    if not settings.telegram_ssl_verify:
        logger.warning(
            "TELEGRAM_SSL_VERIFY=false — TLS certificate verification is disabled"
        )
        session._connector_init["ssl"] = False
    return session


def create_bot(settings: Settings) -> Bot:
    """Create an aiogram Bot with HTML parse mode by default."""
    return Bot(
        token=settings.bot_token,
        session=_build_session(settings),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    """
    Build a fully configured Dispatcher.

    - FSM storage (MemoryStorage; swap for Redis in production if needed)
    - Workflow data (``settings`` injectable into handlers / lifecycle)
    - Middlewares
    - Routers
    - Startup / shutdown hooks
    """
    dispatcher = Dispatcher(storage=MemoryStorage())

    # Available as handler/lifecycle dependency via name ``settings``.
    dispatcher["settings"] = settings

    setup_middlewares(dispatcher, settings)
    dispatcher.include_router(setup_routers(settings))

    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)

    logger.debug(
        "Dispatcher ready (routers=%s, middlewares registered)",
        len(dispatcher.sub_routers),
    )
    return dispatcher
