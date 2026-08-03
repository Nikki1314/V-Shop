"""Shared helpers for SQLAlchemy Enum columns."""

from enum import Enum as PyEnum
from typing import Any


def enum_values(enum_cls: type[PyEnum]) -> list[Any]:
    """Persist StrEnum *values* (e.g. 'ru') instead of member names (e.g. 'RU')."""
    return [item.value for item in enum_cls]
