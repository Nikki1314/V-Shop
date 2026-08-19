"""Aggregate queries behind the statistics dashboard.

Everything here aggregates in the database. Counting orders or summing revenue
in Python would mean streaming the whole order history into the bot process on
every dashboard open, which gets slower exactly as the shop succeeds.

Portability note: ``COUNT(...) FILTER (WHERE ...)`` is cleaner but the test suite
runs on SQLite, so conditional counts use ``SUM(CASE WHEN ... THEN 1 ELSE 0 END)``
which every backend understands and which optimises identically on PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cart import Cart
from app.models.category import Category, Subcategory
from app.models.enums import OrderStatus
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.user import User
from app.repositories.visibility import only_sellable_products


@dataclass(frozen=True, slots=True)
class ProductPopularity:
    """How many distinct completed orders contained a product."""

    product_id: int
    name_ru: str
    name_en: str
    name_de: str
    name_uk: str
    order_count: int


def _count_if(condition: ColumnElement[bool]) -> ColumnElement[int]:
    """Portable conditional count."""
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


class StatisticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- general ---------------------------------------------------------------

    async def entity_counts(self) -> dict[str, int]:
        """
        Row counts for the dashboard header, in a single round trip.

        Both totals and active counts are returned: the catalog entities are
        reported as "active" in the product spec, while orders and users have no
        active/inactive notion.
        """
        stmt = select(
            select(func.count()).select_from(User).scalar_subquery().label("users"),
            select(func.count()).select_from(Category).scalar_subquery().label("categories"),
            select(func.count())
            .select_from(Category)
            .where(Category.is_active.is_(True))
            .scalar_subquery()
            .label("active_categories"),
            select(func.count())
            .select_from(Subcategory)
            .scalar_subquery()
            .label("subcategories"),
            select(func.count())
            .select_from(Subcategory)
            .where(Subcategory.is_active.is_(True))
            .scalar_subquery()
            .label("active_subcategories"),
            select(func.count()).select_from(Product).scalar_subquery().label("products"),
            select(func.count())
            .select_from(Product)
            .where(Product.is_active.is_(True))
            .scalar_subquery()
            .label("active_products"),
            select(func.count()).select_from(Order).scalar_subquery().label("orders"),
            select(func.count()).select_from(Cart).scalar_subquery().label("carts"),
        )
        row = (await self.session.execute(stmt)).one()
        return {key: int(value or 0) for key, value in row._mapping.items()}

    # --- orders ----------------------------------------------------------------

    @staticmethod
    def _order_counts_select(
        *,
        since: datetime | None,
        until: datetime | None,
    ) -> Select[tuple[int, int, int]]:
        stmt = select(
            func.count().label("total"),
            _count_if(Order.status == OrderStatus.COMPLETED).label("completed"),
            _count_if(Order.status == OrderStatus.CANCELLED).label("cancelled"),
        ).select_from(Order)
        if since is not None:
            stmt = stmt.where(Order.created_at >= since)
        if until is not None:
            stmt = stmt.where(Order.created_at < until)
        return stmt

    async def order_counts(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, int]:
        """``total`` / ``completed`` / ``cancelled`` over a half-open range."""
        row = (
            await self.session.execute(self._order_counts_select(since=since, until=until))
        ).one()
        return {key: int(value or 0) for key, value in row._mapping.items()}

    # --- revenue ---------------------------------------------------------------

    async def completed_revenue(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Decimal:
        """
        Revenue from completed orders only.

        Read from ``orders.total_price``, the amount charged at the time, so
        historical revenue never moves when a product is repriced.
        """
        stmt = select(func.coalesce(func.sum(Order.total_price), 0)).where(
            Order.status == OrderStatus.COMPLETED
        )
        if since is not None:
            stmt = stmt.where(Order.created_at >= since)
        if until is not None:
            stmt = stmt.where(Order.created_at < until)
        value = await self.session.scalar(stmt)
        return Decimal(str(value or 0))

    # --- popularity ------------------------------------------------------------

    async def most_ordered_products(self, *, limit: int = 3) -> list[ProductPopularity]:
        """
        Products on sale appearing in the most distinct completed orders.

        A product ordered twice within one order counts once, per the spec.

        Restricted to sellable products, the same set the bottom list ranks: the
        two are opposite ends of one ranking, and a retired bestseller the admin
        can no longer see in the catalog does not belong at the top of it.
        """
        order_count = func.count(distinct(OrderItem.order_id)).label("order_count")
        stmt = only_sellable_products(
            select(
                Product.id,
                Product.name_ru,
                Product.name_en,
                Product.name_de,
                Product.name_uk,
                order_count,
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(Order.status == OrderStatus.COMPLETED)
        )
        stmt = (
            stmt.group_by(
                Product.id,
                Product.name_ru,
                Product.name_en,
                Product.name_de,
                Product.name_uk,
            )
            .order_by(order_count.desc(), Product.id.asc())
            .limit(limit)
        )
        return [ProductPopularity(*row) for row in (await self.session.execute(stmt)).all()]

    async def least_ordered_products(self, *, limit: int = 3) -> list[ProductPopularity]:
        """
        Products on sale appearing in the fewest distinct completed orders.

        Driven from ``products`` with an outer join, so a product that has never
        sold reports zero and qualifies — the whole point of this list.

        Restricted to sellable products: a product the admin has already hidden,
        or one sitting under a deactivated brand or category, is not selling
        because nobody can see it. Listing it as a worst seller is noise.
        """
        completed_items = (
            select(
                OrderItem.product_id.label("product_id"),
                OrderItem.order_id.label("order_id"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status == OrderStatus.COMPLETED)
            .subquery()
        )
        order_count = func.count(distinct(completed_items.c.order_id)).label("order_count")
        stmt = only_sellable_products(
            select(
                Product.id,
                Product.name_ru,
                Product.name_en,
                Product.name_de,
                Product.name_uk,
                order_count,
            )
            .select_from(Product)
            .outerjoin(completed_items, completed_items.c.product_id == Product.id)
        )
        stmt = (
            stmt.group_by(
                Product.id,
                Product.name_ru,
                Product.name_en,
                Product.name_de,
                Product.name_uk,
            )
            .order_by(order_count.asc(), Product.id.asc())
            .limit(limit)
        )
        return [ProductPopularity(*row) for row in (await self.session.execute(stmt)).all()]
