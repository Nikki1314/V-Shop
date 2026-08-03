"""Category repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_ordered(self) -> list[Category]:
        result = await self.session.scalars(
            select(Category).order_by(Category.sort_order.asc(), Category.id.asc())
        )
        return list(result.all())

    async def get_with_products(self, category_id: int) -> Category | None:
        result = await self.session.scalars(
            select(Category)
            .where(Category.id == category_id)
            .options(selectinload(Category.products))
        )
        return result.first()

    async def get_by_name(self, name: str) -> Category | None:
        result = await self.session.scalars(
            select(Category).where(Category.name == name)
        )
        return result.first()

    async def next_sort_order(self) -> int:
        result = await self.session.scalar(select(func.max(Category.sort_order)))
        return int(result or 0) + 1

    async def count_products(self, category_id: int) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(Product).where(Product.category_id == category_id)
        )
        return int(result or 0)

    async def create_category(self, name: str, sort_order: int = 0) -> Category:
        return await self.create_and_add(name=name, sort_order=sort_order)

    async def rename(self, category: Category, name: str) -> Category:
        return await self.update(category, name=name)

    async def set_sort_order(self, category: Category, sort_order: int) -> Category:
        return await self.update(category, sort_order=sort_order)

    async def reorder(self, ordered_ids: list[int]) -> list[Category]:
        """Assign sort_order by position in ordered_ids (0-based) — one SELECT."""
        if not ordered_ids:
            return []

        result = await self.session.scalars(
            select(Category).where(Category.id.in_(ordered_ids))
        )
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
