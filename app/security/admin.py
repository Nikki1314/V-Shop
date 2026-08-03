"""Admin authorization helpers based on ADMIN_IDS."""

from __future__ import annotations

from aiogram.types import User

from app.config import Settings, get_settings


def is_admin_id(telegram_id: int | None, settings: Settings | None = None) -> bool:
    """Return True when ``telegram_id`` is listed in ADMIN_IDS."""
    if telegram_id is None:
        return False
    cfg = settings or get_settings()
    return telegram_id in cfg.admin_ids


def is_admin_user(user: User | None, settings: Settings | None = None) -> bool:
    """Return True when the Telegram user is an authorized admin."""
    if user is None:
        return False
    return is_admin_id(user.id, settings)
