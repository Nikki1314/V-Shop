"""HTML helpers for Telegram ParseMode.HTML messages."""

from __future__ import annotations

from html import escape as html_escape


def e(value: object) -> str:
    """Escape a value for safe interpolation into HTML Telegram messages."""
    if value is None:
        return ""
    return html_escape(str(value), quote=False)
