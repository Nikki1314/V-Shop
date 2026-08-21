"""Small process-local TTL caches for hot, mostly-static reads."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from app.models.category import Category

T = TypeVar("T")


@dataclass
class _Entry[T]:
    value: T
    expires_at: float


class TtlCache[T]:
    """Single-value TTL cache (process-local; not shared across workers)."""

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._entry: _Entry[T] | None = None

    def get(self) -> T | None:
        entry = self._entry
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._entry = None
            return None
        return entry.value

    def set(self, value: T) -> None:
        self._entry = _Entry(value=value, expires_at=time.monotonic() + self.ttl_seconds)

    def clear(self) -> None:
        self._entry = None


# Categories change rarely; 60s is enough to cut list_ordered spam.
categories_list_cache: TtlCache[list[Category]] = TtlCache(ttl_seconds=60.0)


def invalidate_categories_cache() -> None:
    categories_list_cache.clear()
