"""Shop statistics for the admin dashboard.

Assembles the numbers; renders nothing. Month boundaries come from
``APP_TIMEZONE`` rather than the server clock, and every figure is aggregated in
SQL — see :mod:`app.repositories.statistics`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.statistics import ProductPopularity, StatisticsRepository
from app.utils.periods import MonthBounds, month_bounds

TOP_PRODUCTS_LIMIT = 3


@dataclass(frozen=True, slots=True)
class GeneralStats:
    users: int = 0
    categories: int = 0
    active_categories: int = 0
    subcategories: int = 0
    active_subcategories: int = 0
    products: int = 0
    active_products: int = 0
    orders: int = 0
    carts: int = 0


@dataclass(frozen=True, slots=True)
class OrderCounts:
    total: int = 0
    completed: int = 0
    cancelled: int = 0

    @property
    def other(self) -> int:
        """Orders in a status that is neither completed nor cancelled."""
        return self.total - self.completed - self.cancelled


@dataclass(frozen=True, slots=True)
class PeriodStats:
    """One reporting window: how many orders, and how much completed revenue."""

    orders: OrderCounts = field(default_factory=OrderCounts)
    revenue: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class ShopStatistics:
    general: GeneralStats
    all_time: PeriodStats
    current_month: PeriodStats
    previous_month: PeriodStats
    most_ordered: list[ProductPopularity]
    least_ordered: list[ProductPopularity]
    bounds: MonthBounds
    timezone: str


class StatisticsService:
    """
    Assemble the admin dashboard.

    ``timezone`` is injected, not read from the global settings: handlers already
    receive ``settings``, so the call site is ``StatisticsService(session,
    settings.app_timezone)``. Omitting it falls back to :data:`DEFAULT_TIMEZONE`,
    which is also the config default — the two are pinned together by
    ``test_config_default_matches_the_period_helper``.
    """

    def __init__(self, session: AsyncSession, timezone: str | None = None) -> None:
        self.session = session
        self.stats = StatisticsRepository(session)
        self.timezone = timezone

    async def collect(self, now: datetime | None = None) -> ShopStatistics:
        """
        Build the whole dashboard.

        Nine aggregate queries regardless of how much history the shop has.
        """
        bounds = month_bounds(now, self.timezone)
        current_start, next_start = bounds.current
        previous_start, previous_end = bounds.previous

        general = GeneralStats(**await self.stats.entity_counts())

        all_time = await self._period()
        current = await self._period(since=current_start, until=next_start)
        previous = await self._period(since=previous_start, until=previous_end)

        return ShopStatistics(
            general=general,
            all_time=all_time,
            current_month=current,
            previous_month=previous,
            most_ordered=await self.stats.most_ordered_products(limit=TOP_PRODUCTS_LIMIT),
            least_ordered=await self.stats.least_ordered_products(limit=TOP_PRODUCTS_LIMIT),
            bounds=bounds,
            timezone=str(getattr(bounds.current_start.tzinfo, "key", bounds.current_start.tzinfo)),
        )

    async def _period(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> PeriodStats:
        counts = await self.stats.order_counts(since=since, until=until)
        revenue = await self.stats.completed_revenue(since=since, until=until)
        return PeriodStats(orders=OrderCounts(**counts), revenue=revenue)
