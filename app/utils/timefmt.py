"""Shared timestamp formatting."""

from __future__ import annotations

from datetime import datetime


def format_timestamp(value: datetime | None, *, with_seconds: bool = False) -> str:
    if value is None:
        return "—"
    pattern = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    if value.tzinfo is None:
        return value.strftime(pattern)
    if with_seconds:
        return value.strftime("%Y-%m-%d %H:%M:%S %Z")
    return value.strftime(pattern)
