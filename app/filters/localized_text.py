"""Filter that matches Reply Keyboard labels across all locales."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.utils.i18n import translations_for_cached


class LocalizedText(BaseFilter):
    """
    Match a message against every translation of a locale key.

    Example::

        @router.message(LocalizedText("menu.catalog"))
        async def open_catalog(...):
            ...
    """

    def __init__(self, key: str) -> None:
        self.key = key
        self._texts = translations_for_cached(key)
        if not self._texts:
            raise ValueError(f"No translations found for locale key {key!r}")

    async def __call__(self, message: Message) -> bool:
        return message.text is not None and message.text in self._texts
