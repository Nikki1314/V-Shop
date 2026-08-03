"""Catalog service — categories and products for browsing."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product
from app.repositories.category import CategoryRepository
from app.repositories.product import ProductRepository
from app.utils.cache import categories_list_cache


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.categories = CategoryRepository(session)
        self.products = ProductRepository(session)

    async def list_categories(self) -> list[Category]:
        """Categories in display order (TTL-cached, detached instances)."""
        cached = categories_list_cache.get()
        if cached is not None:
            return cached

        categories = await self.categories.list_ordered()
        for category in categories:
            self.session.expunge(category)
        categories_list_cache.set(categories)
        return categories

    async def get_category(self, category_id: int) -> Category | None:
        return await self.categories.get_by_id(category_id)

    async def list_products(self, category_id: int) -> list[Product]:
        """Active products in a category."""
        return await self.products.list_by_category(category_id, active_only=True)

    async def get_category_with_products(
        self,
        category_id: int,
    ) -> tuple[Category | None, list[Product]]:
        """Load category then its active products (sequential; one session)."""
        category = await self.get_category(category_id)
        products = await self.list_products(category_id)
        return category, products

    async def get_active_product(self, product_id: int) -> Product | None:
        return await self.products.get_active_by_id(product_id)
