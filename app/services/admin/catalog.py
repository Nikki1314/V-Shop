"""Admin catalog operations (categories + products)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product
from app.repositories.category import CategoryRepository
from app.repositories.product import ProductRepository
from app.services.admin.exceptions import CategoryInUseError, ProductInUseError
from app.utils.cache import categories_list_cache, invalidate_categories_cache


class AdminCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.categories = CategoryRepository(session)

    async def list_categories(self) -> list[Category]:
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

    async def get_category_by_name(self, name: str) -> Category | None:
        return await self.categories.get_by_name(name)

    async def create_category(self, name: str) -> Category:
        sort_order = await self.categories.next_sort_order()
        category = await self.categories.create_category(name=name, sort_order=sort_order)
        invalidate_categories_cache()
        return category

    async def rename_category(self, category: Category, name: str) -> Category:
        category = await self.categories.rename(category, name)
        invalidate_categories_cache()
        return category

    async def delete_category(self, category: Category) -> None:
        product_count = await self.categories.count_products(category.id)
        if product_count > 0:
            raise CategoryInUseError(
                f"Category {category.id} still has {product_count} product(s)"
            )
        await self.categories.delete(category)
        invalidate_categories_cache()

    async def move_category(self, category_id: int, *, direction: int) -> list[Category]:
        categories = await self.categories.move(category_id, direction=direction)
        invalidate_categories_cache()
        return categories

    async def count_category_products(self, category_id: int) -> int:
        return await self.categories.count_products(category_id)

    async def list_products(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Product]:
        return await self.products.list_all_admin(offset=offset, limit=limit)

    async def count_products(self) -> int:
        return await self.products.count_all()

    async def page_products(
        self,
        *,
        offset: int = 0,
        limit: int,
    ) -> tuple[int, list[Product]]:
        total = await self.count_products()
        items = await self.list_products(offset=offset, limit=limit)
        return total, items

    async def get_product(self, product_id: int) -> Product | None:
        return await self.products.get_with_category(product_id)

    async def create_product(
        self,
        *,
        category_id: int,
        name_ru: str,
        name_en: str,
        name_de: str,
        description_ru: str,
        description_en: str,
        description_de: str,
        flavor: str,
        volume: str,
        nicotine_strength: str,
        price: Decimal | str | float,
        image_file_id: str | None = None,
        is_active: bool = True,
    ) -> Product:
        return await self.products.create_product(
            category_id=category_id,
            name_ru=name_ru,
            name_en=name_en,
            name_de=name_de,
            description_ru=description_ru,
            description_en=description_en,
            description_de=description_de,
            flavor=flavor,
            volume=volume,
            nicotine_strength=nicotine_strength,
            price=price,
            image_file_id=image_file_id,
            is_active=is_active,
        )

    async def update_product(self, product: Product, **fields: Any) -> Product:
        return await self.products.update_product(product, **fields)

    async def set_product_price(self, product: Product, price: Decimal | str | float) -> Product:
        return await self.products.update_product(product, price=price)

    async def set_product_descriptions(
        self,
        product: Product,
        *,
        description_ru: str,
        description_en: str,
        description_de: str,
    ) -> Product:
        return await self.products.update_product(
            product,
            description_ru=description_ru,
            description_en=description_en,
            description_de=description_de,
        )

    async def enable_product(self, product: Product) -> Product:
        return await self.products.enable(product)

    async def disable_product(self, product: Product) -> Product:
        return await self.products.disable(product)

    async def delete_product(self, product: Product) -> None:
        refs = await self.products.count_order_references(product.id)
        if refs > 0:
            raise ProductInUseError(
                f"Product {product.id} is referenced by {refs} order item(s)"
            )
        await self.products.delete(product)
