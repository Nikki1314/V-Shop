"""Aiogram middlewares package."""

from __future__ import annotations

import logging

from aiogram import Dispatcher

from app.config import Settings
from app.errors.handlers import setup_error_handlers
from app.middlewares.database import DatabaseMiddleware
from app.middlewares.error import ErrorHandlingMiddleware
from app.middlewares.i18n import LocalizationMiddleware
from app.middlewares.request_log import LoggingMiddleware

logger = logging.getLogger(__name__)


def setup_middlewares(dispatcher: Dispatcher, settings: Settings) -> None:
    """
    Register outer update middlewares (order matters — first = outermost).

    1. LoggingMiddleware — request/response timing
    2. ErrorHandlingMiddleware — user-facing errors after DB rollback
    3. DatabaseMiddleware — opens ``session``, commit/rollback
    4. LocalizationMiddleware — loads ``db_user`` / ``i18n``

    Also registers the dispatcher ``errors`` handler as a final safety net.
    """
    _ = settings

    logging_mw = LoggingMiddleware()
    error_mw = ErrorHandlingMiddleware()
    database = DatabaseMiddleware()
    localization = LocalizationMiddleware()

    dispatcher.update.outer_middleware(logging_mw)
    dispatcher.update.outer_middleware(error_mw)
    dispatcher.update.outer_middleware(database)
    dispatcher.update.outer_middleware(localization)
    setup_error_handlers(dispatcher)

    logger.debug(
        "Middlewares registered: Logging, ErrorHandling, Database, Localization; "
        "dispatcher error handler enabled"
    )
