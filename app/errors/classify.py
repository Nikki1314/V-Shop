"""Centralized error classification and safe user messaging."""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

logger = logging.getLogger(__name__)

try:
    from aiohttp import ClientError as AiohttpClientError
except ImportError:  # pragma: no cover
    AiohttpClientError = ()  # type: ignore[misc, assignment]


class ErrorKind(StrEnum):
    TELEGRAM = "telegram"
    DATABASE = "database"
    NETWORK = "network"
    UNEXPECTED = "unexpected"


_LOCALE_KEYS: dict[ErrorKind, str] = {
    ErrorKind.TELEGRAM: "error.telegram",
    ErrorKind.DATABASE: "error.database",
    ErrorKind.NETWORK: "error.network",
    ErrorKind.UNEXPECTED: "error.generic",
}


def classify_error(exc: BaseException) -> ErrorKind:
    """Map an exception to a stable error category (no user-facing details)."""
    if isinstance(exc, TelegramNetworkError):
        return ErrorKind.NETWORK
    if isinstance(exc, (TelegramRetryAfter, TelegramAPIError)):
        return ErrorKind.TELEGRAM
    if isinstance(exc, (SQLAlchemyError, DBAPIError)):
        return ErrorKind.DATABASE
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)):
        return ErrorKind.NETWORK
    if AiohttpClientError and isinstance(exc, AiohttpClientError):
        return ErrorKind.NETWORK
    # asyncpg / driver errors often wrap as Exception subclasses
    module = type(exc).__module__ or ""
    if module.startswith("asyncpg") or module.startswith("aiohttp"):
        return ErrorKind.NETWORK if "connect" in type(exc).__name__.lower() else ErrorKind.DATABASE
    return ErrorKind.UNEXPECTED


def locale_key_for_error(exc: BaseException) -> str:
    """Locale key for a user-safe message (never includes exception text)."""
    return _LOCALE_KEYS[classify_error(exc)]


def log_handled_error(
    exc: BaseException,
    *,
    update_id: int | None = None,
    user_id: int | None = None,
) -> ErrorKind:
    """
    Log full diagnostics server-side.

    Stack traces stay in logs only — never returned to Telegram users.
    """
    kind = classify_error(exc)
    logger.exception(
        "Handled application error kind=%s type=%s update_id=%s user_id=%s",
        kind.value,
        type(exc).__name__,
        update_id,
        user_id,
    )
    return kind
