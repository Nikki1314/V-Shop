"""Centralized logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(settings: Settings) -> None:
    """Configure root and third-party loggers based on application settings."""
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(handler)

    # Keep noisy libraries quieter unless debugging.
    logging.getLogger("aiogram").setLevel(logging.INFO if level <= logging.INFO else level)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.is_development else logging.WARNING
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logging.getLogger(__name__).debug(
        "Logging configured (env=%s, level=%s)",
        settings.app_env,
        level_name,
    )
