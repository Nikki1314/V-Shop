"""Aiogram middlewares package."""

from __future__ import annotations

import logging

from aiogram import Dispatcher

from app.config import Settings
from app.errors.handlers import setup_error_handlers
from app.middlewares.database import DatabaseMiddleware
from app.middlewares.error import ErrorHandlingMiddleware
from app.middlewares.i18n import LocalizationMiddleware
from app.middlewares.private_chat import PrivateChatMiddleware
from app.middlewares.request_log import LoggingMiddleware

logger = logging.getLogger(__name__)


def setup_middlewares(dispatcher: Dispatcher, settings: Settings) -> None:
    """
    Register outer update middlewares (order matters — first = outermost).

    1. LoggingMiddleware — request/response timing
    2. PrivateChatMiddleware — drop group/supergroup traffic before any I/O
    3. ErrorHandlingMiddleware — user-facing errors after DB rollback
    4. DatabaseMiddleware — opens ``session``, commit/rollback
    5. LocalizationMiddleware — loads ``db_user`` / ``i18n``

    Private-chat isolation sits ahead of both the error handler and the
    database. Ahead of the database so a group update never opens a session;
    ahead of the error handler so a failure downstream can never cause a reply
    into a group. ``notify_user_of_error`` enforces the same rule again at the
    send site, for the paths aiogram handles itself.

    Also registers the dispatcher ``errors`` handler as a final safety net.
    """
    _ = settings

    logging_mw = LoggingMiddleware()
    error_mw = ErrorHandlingMiddleware()
    private_chat = PrivateChatMiddleware()
    database = DatabaseMiddleware()
    localization = LocalizationMiddleware()

    dispatcher.update.outer_middleware(logging_mw)
    dispatcher.update.outer_middleware(private_chat)
    dispatcher.update.outer_middleware(error_mw)
    dispatcher.update.outer_middleware(database)
    dispatcher.update.outer_middleware(localization)
    setup_error_handlers(dispatcher)

    logger.debug(
        "Middlewares registered: Logging, PrivateChat, ErrorHandling, Database, "
        "Localization; "
        "dispatcher error handler enabled"
    )
