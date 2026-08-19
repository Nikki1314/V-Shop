"""Reporting periods anchored to the shop's configured time zone.

Month boundaries must not follow the server clock: a shop in Berlin closing its
books at midnight local time gets different numbers from a UTC server for one or
two hours every day, and the gap widens across a DST change. Every boundary here
is built in ``APP_TIMEZONE`` and returned as an aware datetime, so PostgreSQL
compares it against ``timestamptz`` correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Berlin"


def resolve_timezone(name: str | None = None) -> ZoneInfo:
    """
    Return the configured zone, falling back to the default then to UTC.

    A bad ``APP_TIMEZONE`` must not stop the bot booting; statistics degrade to
    the fallback zone instead.
    """
    for candidate in (name, DEFAULT_TIMEZONE, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    raise RuntimeError("No usable time zone database is available")


@dataclass(frozen=True, slots=True)
class MonthBounds:
    """Half-open ``[start, end)`` ranges for the current and previous month."""

    current_start: datetime
    previous_start: datetime
    next_start: datetime

    @property
    def current(self) -> tuple[datetime, datetime]:
        return self.current_start, self.next_start

    @property
    def previous(self) -> tuple[datetime, datetime]:
        return self.previous_start, self.current_start


def month_start(moment: datetime) -> datetime:
    """Midnight on the first of ``moment``'s month, keeping its zone."""
    return moment.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


def month_bounds(now: datetime | None = None, timezone: str | None = None) -> MonthBounds:
    """
    Month boundaries around ``now`` in the configured zone.

    Ranges are half-open so an order created exactly at midnight belongs to the
    month starting then, and never to both.
    """
    tz = resolve_timezone(timezone)
    moment = (now.astimezone(tz) if now is not None else datetime.now(tz))

    current = month_start(moment)
    previous = month_start(
        current.replace(year=current.year - 1, month=12)
        if current.month == 1
        else current.replace(month=current.month - 1)
    )
    following = (
        current.replace(year=current.year + 1, month=1)
        if current.month == 12
        else current.replace(month=current.month + 1)
    )
    return MonthBounds(
        current_start=current, previous_start=previous, next_start=following
    )
