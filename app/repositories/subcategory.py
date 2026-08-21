"""Subcategory (brand) repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.repositories.base import BaseRepository

LOCALIZED_NAME_FIELDS = ("name_ru", "name_en", "name_de", "name_uk")


class SubcategoryRepository(BaseRepository[Subcategory]):
    model = Subcategory

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # --- read ------------------------------------------------------------------

    @staticmethod
    def _ordered(stmt: Select[Any]) -> Select[Any]:
        return stmt.order_by(Subcategory.sort_order.asc(), Subcategory.id.asc())

    async def list_by_category(
        self,
        category_id: int,
        *,
        active_only: bool = False,
    ) -> list[Subcategory]:
        """Subcategories of a category in display order."""
        stmt = select(Subcategory).where(Subcategory.category_id == category_id)
        if active_only:
            stmt = stmt.where(Subcategory.is_active.is_(True))
        result = await self.session.scalars(self._ordered(stmt))
        return list(result.all())

    async def list_visible_by_category(self, category_id: int) -> list[Subcategory]:
        """
        Customer-visible subcategories.

        Joins the parent so an active brand under a deactivated category is
        correctly hidden — checking ``Subcategory.is_active`` alone is not enough.
        """
        stmt = (
            select(Subcategory)
            .join(Category, Category.id == Subcategory.category_id)
            .where(
                Subcategory.category_id == category_id,
                Subcategory.is_active.is_(True),
                Category.is_active.is_(True),
            )
        )
        result = await self.session.scalars(self._ordered(stmt))
        return list(result.all())

    async def list_with_counts(
        self,
        category_id: int,
        *,
        active_only: bool = False,
    ) -> list[tuple[Subcategory, int]]:
        """``(subcategory, product_count)`` in a single query — never N+1."""
        product_count = (
            select(func.count(Product.id))
            .where(Product.subcategory_id == Subcategory.id)
            .correlate(Subcategory)
            .scalar_subquery()
        )
        stmt = select(Subcategory, product_count).where(Subcategory.category_id == category_id)
        if active_only:
            stmt = stmt.where(Subcategory.is_active.is_(True))
        rows = await self.session.execute(self._ordered(stmt))
        return [(s, int(c or 0)) for s, c in rows.all()]

    async def get_with_products(self, subcategory_id: int) -> Subcategory | None:
        result = await self.session.scalars(
            select(Subcategory)
            .where(Subcategory.id == subcategory_id)
            .options(selectinload(Subcategory.products))
        )
        return result.first()

    async def get_with_category(self, subcategory_id: int) -> Subcategory | None:
        result = await self.session.scalars(
            select(Subcategory)
            .where(Subcategory.id == subcategory_id)
            .options(selectinload(Subcategory.category))
        )
        return result.first()

    async def get_visible_by_id(self, subcategory_id: int) -> Subcategory | None:
        """A subcategory a customer may open: active, under an active category."""
        result = await self.session.scalars(
            select(Subcategory)
            .join(Category, Category.id == Subcategory.category_id)
            .where(
                Subcategory.id == subcategory_id,
                Subcategory.is_active.is_(True),
                Category.is_active.is_(True),
            )
        )
        return result.first()

    async def count_by_category(self, category_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Subcategory)
            .where(Subcategory.category_id == category_id)
        )
        return int(result or 0)

    async def count_products(self, subcategory_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.subcategory_id == subcategory_id)
        )
        return int(result or 0)

    async def next_sort_order(self, category_id: int) -> int:
        result = await self.session.scalar(
            select(func.max(Subcategory.sort_order)).where(Subcategory.category_id == category_id)
        )
        return int(result or 0) + 1

    # --- write -----------------------------------------------------------------

    async def create_subcategory(
        self,
        *,
        category_id: int,
        name: str,
        sort_order: int | None = None,
        name_ru: str | None = None,
        name_en: str | None = None,
        name_de: str | None = None,
        name_uk: str | None = None,
        is_active: bool = True,
    ) -> Subcategory:
        """Create a subcategory; unset localized names fall back to ``name``."""
        if sort_order is None:
            sort_order = await self.next_sort_order(category_id)
        return await self.create_and_add(
            category_id=category_id,
            name_ru=name_ru or name,
            name_en=name_en or name,
            name_de=name_de or name,
            name_uk=name_uk or name,
            sort_order=sort_order,
            is_active=is_active,
        )

    async def rename(self, subcategory: Subcategory, name: str) -> Subcategory:
        """Set every localized name to the same value."""
        return await self.update(
            subcategory,
            name_ru=name,
            name_en=name,
            name_de=name,
            name_uk=name,
        )

    async def set_names(self, subcategory: Subcategory, **names: str) -> Subcategory:
        """Update individual localized names (``name_ru=...``, ``name_uk=...``)."""
        unknown = set(names) - set(LOCALIZED_NAME_FIELDS)
        if unknown:
            raise ValueError(f"Unknown localized name fields: {sorted(unknown)}")
        return await self.update(subcategory, **names)

    async def set_active(self, subcategory: Subcategory, is_active: bool) -> Subcategory:
        return await self.update(subcategory, is_active=is_active)

    async def set_sort_order(self, subcategory: Subcategory, sort_order: int) -> Subcategory:
        return await self.update(subcategory, sort_order=sort_order)

    async def move_to_category(
        self,
        subcategory: Subcategory,
        category_id: int,
    ) -> Subcategory:
        """Reassign a brand to another category, appending it to that order."""
        sort_order = await self.next_sort_order(category_id)
        return await self.update(subcategory, category_id=category_id, sort_order=sort_order)

    async def reorder(self, category_id: int, ordered_ids: list[int]) -> list[Subcategory]:
        """Assign sort_order by position within one category — one SELECT."""
        if not ordered_ids:
            return []
        result = await self.session.scalars(
            select(Subcategory).where(
                Subcategory.id.in_(ordered_ids),
                Subcategory.category_id == category_id,
            )
        )
        by_id = {sub.id: sub for sub in result.all()}

        ordered: list[Subcategory] = []
        for index, sub_id in enumerate(ordered_ids):
            sub = by_id.get(sub_id)
            if sub is None:
                continue
            sub.sort_order = index
            ordered.append(sub)
        await self.session.flush()
        return ordered

    async def move(
        self,
        category_id: int,
        subcategory_id: int,
        *,
        direction: int,
    ) -> list[Subcategory]:
        """Move one step up (-1) or down (+1) within its category."""
        subs = await self.list_by_category(category_id)
        index = next((i for i, s in enumerate(subs) if s.id == subcategory_id), None)
        if index is None:
            return subs
        new_index = index + direction
        if new_index < 0 or new_index >= len(subs):
            return subs
        subs[index], subs[new_index] = subs[new_index], subs[index]
        return await self.reorder(category_id, [s.id for s in subs])
