"""Application entrypoint."""

from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramUnauthorizedError

from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def run() -> None:
    """
    Bootstrap logging, bot, dispatcher, then start long-polling.

    Startup / shutdown side-effects live in ``app.lifecycle`` and are
    registered on the dispatcher (aiogram 3 best practice).
    """
    settings = get_settings()
    setup_logging(settings)

    logger.info("Bootstrapping V-Shop bot (env=%s)", settings.app_env)

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings)

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_signals=True,
        )
    except TelegramUnauthorizedError:
        logger.exception("Telegram rejected BOT_TOKEN. Set a valid token in .env and retry.")
        raise
    finally:
        await bot.session.close()
        logger.info("Bot HTTP session closed")


def main() -> None:
    """Synchronous CLI entrypoint used by ``python -m app.main``."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
