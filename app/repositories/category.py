"""Category repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.repositories.base import BaseRepository

LOCALIZED_NAME_FIELDS = ("name_ru", "name_en", "name_de", "name_uk")


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # --- read ------------------------------------------------------------------

    @staticmethod
    def _ordered(stmt: Select[Any]) -> Select[Any]:
        return stmt.order_by(Category.sort_order.asc(), Category.id.asc())

    async def list_ordered(self, *, active_only: bool = False) -> list[Category]:
        stmt = select(Category)
        if active_only:
            stmt = stmt.where(Category.is_active.is_(True))
        result = await self.session.scalars(self._ordered(stmt))
        return list(result.all())

    async def list_with_subcategories(
        self,
        *,
        active_only: bool = False,
    ) -> list[Category]:
        """
        Categories with their subcategories eagerly loaded.

        Two queries total regardless of row count (``selectinload``), never N+1.
        When ``active_only`` the nested subcategories are filtered too, so an
        inactive brand never reaches a customer through its parent.
        """
        stmt = select(Category)
        if active_only:
            stmt = stmt.where(Category.is_active.is_(True))
            loader = selectinload(
                Category.subcategories.and_(Subcategory.is_active.is_(True))
            )
        else:
            loader = selectinload(Category.subcategories)
        result = await self.session.scalars(self._ordered(stmt).options(loader))
        return list(result.unique().all())

    async def list_with_counts(
        self,
        *,
        active_only: bool = False,
    ) -> list[tuple[Category, int, int]]:
        """
        ``(category, subcategory_count, product_count)`` in a single query.

        Correlated scalar subqueries keep this to one round trip; counting per
        category in Python would be N+1.
        """
        sub_count = (
            select(func.count(Subcategory.id))
            .where(Subcategory.category_id == Category.id)
            .correlate(Category)
            .scalar_subquery()
        )
        product_count = (
            select(func.count(Product.id))
            .where(Product.category_id == Category.id)
            .correlate(Category)
            .scalar_subquery()
        )
        stmt = select(Category, sub_count, product_count)
        if active_only:
            stmt = stmt.where(Category.is_active.is_(True))
        rows = await self.session.execute(self._ordered(stmt))
        return [(c, int(s or 0), int(p or 0)) for c, s, p in rows.all()]

    async def get_with_subcategories(self, category_id: int) -> Category | None:
        result = await self.session.scalars(
            select(Category)
            .where(Category.id == category_id)
            .options(selectinload(Category.subcategories))
        )
        return result.first()

    async def get_active_by_id(self, category_id: int) -> Category | None:
        result = await self.session.scalars(
            select(Category).where(
                Category.id == category_id,
                Category.is_active.is_(True),
            )
        )
        return result.first()

    async def get_with_products(self, category_id: int) -> Category | None:
        result = await self.session.scalars(
            select(Category)
            .where(Category.id == category_id)
            .options(selectinload(Category.products))
        )
        return result.first()

    async def get_by_name(self, name: str) -> Category | None:
        result = await self.session.scalars(select(Category).where(Category.name == name))
        return result.first()

    async def next_sort_order(self) -> int:
        result = await self.session.scalar(select(func.max(Category.sort_order)))
        return int(result or 0) + 1

    async def count_products(self, category_id: int) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(Product).where(Product.category_id == category_id)
        )
        return int(result or 0)

    async def count_subcategories(self, category_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Subcategory)
            .where(Subcategory.category_id == category_id)
        )
        return int(result or 0)

    # --- write -----------------------------------------------------------------

    async def create_category(
        self,
        name: str,
        sort_order: int = 0,
        *,
        name_ru: str | None = None,
        name_en: str | None = None,
        name_de: str | None = None,
        name_uk: str | None = None,
        is_active: bool = True,
    ) -> Category:
        """
        Create a category.

        Any localized name left unset falls back to ``name``, so callers that
        predate the hierarchy keep working and never write NULLs.
        """
        return await self.create_and_add(
            name=name,
            name_ru=name_ru or name,
            name_en=name_en or name,
            name_de=name_de or name,
            name_uk=name_uk or name,
            sort_order=sort_order,
            is_active=is_active,
        )

    async def rename(self, category: Category, name: str) -> Category:
        """Rename a category, keeping the legacy and localized columns in sync."""
        return await self.update(
            category,
            name=name,
            name_ru=name,
            name_en=name,
            name_de=name,
            name_uk=name,
        )

    async def set_names(self, category: Category, **names: str) -> Category:
        """
        Update individual localized names (``name_ru=...``, ``name_uk=...``).

        The legacy ``name`` column tracks the Russian value so existing admin and
        catalog rendering keeps working until it is dropped.
        """
        unknown = set(names) - set(LOCALIZED_NAME_FIELDS)
        if unknown:
            raise ValueError(f"Unknown localized name fields: {sorted(unknown)}")
        fields: dict[str, Any] = dict(names)
        if "name_ru" in fields:
            fields["name"] = fields["name_ru"]
        return await self.update(category, **fields)

    async def set_active(self, category: Category, is_active: bool) -> Category:
        return await self.update(category, is_active=is_active)

    async def set_sort_order(self, category: Category, sort_order: int) -> Category:
        return await self.update(category, sort_order=sort_order)

    async def reorder(self, ordered_ids: list[int]) -> list[Category]:
        """Assign sort_order by position in ordered_ids (0-based) — one SELECT."""
        if not ordered_ids:
            return []

        result = await self.session.scalars(select(Category).where(Category.id.in_(ordered_ids)))
        by_id = {category.id: category for category in result.all()}

        categories: list[Category] = []
        for index, category_id in enumerate(ordered_ids):
            category = by_id.get(category_id)
            if category is None:
                continue
            category.sort_order = index
            categories.append(category)
        await self.session.flush()
        return categories

    async def move(self, category_id: int, *, direction: int) -> list[Category]:
        """
        Move a category one step up (direction=-1) or down (direction=+1).

        Returns the full ordered list after the move.
        """
        categories = await self.list_ordered()
        index = next((i for i, c in enumerate(categories) if c.id == category_id), None)
        if index is None:
            return categories

        new_index = index + direction
        if new_index < 0 or new_index >= len(categories):
            return categories

        categories[index], categories[new_index] = categories[new_index], categories[index]
        return await self.reorder([c.id for c in categories])
