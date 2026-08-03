"""Shared Telegram message edit / answer helpers."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)

KeyboardMarkup = InlineKeyboardMarkup | ReplyKeyboardMarkup | None


async def edit_or_answer(
    message: Message,
    text: str,
    *,
    reply_markup: KeyboardMarkup = None,
    edit: bool = True,
) -> None:
    """Prefer ``edit_text``; fall back to ``answer`` when edit is unavailable."""
    if edit:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except Exception:
            logger.debug("Could not edit message; answering instead", exc_info=True)
    await message.answer(text, reply_markup=reply_markup)


async def clear_inline_markup(message: Message) -> None:
    """Best-effort removal of an inline keyboard."""
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("Could not clear inline keyboard", exc_info=True)


def clamp_page(page: int, total: int, page_size: int) -> int:
    """Clamp a 0-based page index into the valid range for ``total`` items."""
    if total <= 0 or page_size <= 0:
        return 0
    pages = max(1, (total + page_size - 1) // page_size)
    return max(0, min(page, pages - 1))


def page_count(total: int, page_size: int) -> int:
    if total <= 0 or page_size <= 0:
        return 1
    return max(1, (total + page_size - 1) // page_size)


def truncate_button_label(label: str, *, max_len: int = 64) -> str:
    """Telegram inline button text limit."""
    if len(label) <= max_len:
        return label
    if max_len <= 3:
        return label[:max_len]
    return f"{label[: max_len - 3]}..."


def int_from_state(data: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default
