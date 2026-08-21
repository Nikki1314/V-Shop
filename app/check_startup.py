"""Smoke-check bot initialization without entering the polling loop forever.

Usage:
    python -m app.check_startup
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError

from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.database.session import check_db_connection, close_db, init_db
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _is_placeholder_token(token: str) -> bool:
    lowered = token.lower()
    return "your_bot_token" in lowered or token.startswith("123456:")


def _assert_wiring(dispatcher: Dispatcher) -> None:
    assert dispatcher.sub_routers, "No routers mounted on dispatcher"
    root = dispatcher.sub_routers[0]
    assert root.name == "root"
    router_names = {r.name for r in root.sub_routers}
    assert "user" in router_names
    assert "admin" in router_names
    assert "settings" in dispatcher.workflow_data
    assert dispatcher.startup.handlers, "Startup hooks not registered"
    assert dispatcher.shutdown.handlers, "Shutdown hooks not registered"
    logger.info(
        "Wiring OK: routers=%s startup_hooks=%s shutdown_hooks=%s",
        sorted(router_names),
        len(dispatcher.startup.handlers),
        len(dispatcher.shutdown.handlers),
    )


async def check() -> int:
    settings = get_settings()
    setup_logging(settings)

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings)
    _assert_wiring(dispatcher)

    exit_code = 0
    try:
        logger.info("Checking database…")
        await init_db()
        await check_db_connection()
        logger.info("Database OK")

        if _is_placeholder_token(settings.bot_token):
            logger.error(
                "BOT_TOKEN in .env is still a placeholder. "
                "Replace it with a real token from @BotFather to start polling."
            )
            exit_code = 2
        else:
            logger.info("Emitting full startup (includes Telegram getMe)…")
            await dispatcher.emit_startup(bot=bot, settings=settings)
            logger.info("Full startup succeeded — bot is ready to poll")
    except TelegramUnauthorizedError:
        logger.error("BOT_TOKEN is invalid or revoked.")
        exit_code = 2
    except TelegramAPIError as exc:
        logger.error("Telegram API error during startup: %s", exc)
        exit_code = 3
    except Exception:
        logger.exception("Startup check failed")
        exit_code = 1
    finally:
        logger.info("Emitting shutdown…")
        await dispatcher.emit_shutdown(bot=bot, settings=settings)
        await bot.session.close()
        # close_db may already have run via shutdown hook; safe to call again.
        await close_db()
        logger.info("Shutdown finished")

    return exit_code


def main() -> None:
    raise SystemExit(asyncio.run(check()))


if __name__ == "__main__":
    main()
