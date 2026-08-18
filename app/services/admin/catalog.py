"""Admin catalog operations (categories, subcategories, products).

Admin views deliberately show EVERYTHING, including inactive rows — that is the
point of an admin panel. Customer-visible filtering lives in
:class:`app.services.catalog.CatalogService`.

This service does not read the customer category cache: that cache holds only
active categories, so serving it here would silently hide deactivated
categories from admins. Mutations still invalidate it so customers see changes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.repositories.category import CategoryRepository
from app.repositories.product import ProductRepository
from app.repositories.subcategory import SubcategoryRepository
from app.services.admin.exceptions import (
    CategoryInUseError,
    ProductInUseError,
    SubcategoryInUseError,
)
from app.utils.cache import invalidate_categories_cache


class AdminCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.categories = CategoryRepository(session)
        self.subcategories = SubcategoryRepository(session)

    async def list_categories(self, *, active_only: bool = False) -> list[Category]:
        """All categories, including inactive ones. Never served from the cache."""
        return await self.categories.list_ordered(active_only=active_only)

    async def list_categories_with_counts(self) -> list[tuple[Category, int, int]]:
        """``(category, subcategory_count, product_count)`` in a single query."""
        return await self.categories.list_with_counts()

    async def set_category_active(self, category: Category, is_active: bool) -> Category:
        category = await self.categories.set_active(category, is_active)
        invalidate_categories_cache()
        return category

    async def set_category_names(self, category: Category, **names: str) -> Category:
        category = await self.categories.set_names(category, **names)
        invalidate_categories_cache()
        return category

    async def get_category(self, category_id: int) -> Category | None:
        return await self.categories.get_by_id(category_id)

    async def get_category_by_name(self, name: str) -> Category | None:
        return await self.categories.get_by_name(name)

    async def create_category(
        self,
        name: str,
        *,
        name_ru: str | None = None,
        name_en: str | None = None,
        name_de: str | None = None,
        name_uk: str | None = None,
    ) -> Category:
        sort_order = await self.categories.next_sort_order()
        category = await self.categories.create_category(
            name=name,
            sort_order=sort_order,
            name_ru=name_ru,
            name_en=name_en,
            name_de=name_de,
            name_uk=name_uk,
        )
        invalidate_categories_cache()
        return category

    async def rename_category(self, category: Category, name: str) -> Category:
        category = await self.categories.rename(category, name)
        invalidate_categories_cache()
        return category

    async def delete_category(self, category: Category) -> None:
        """Refuse while anything still hangs off the category."""
        subcategory_count = await self.categories.count_subcategories(category.id)
        if subcategory_count > 0:
            raise CategoryInUseError(
                f"Category {category.id} still has {subcategory_count} subcategory(ies)"
            )
        product_count = await self.categories.count_products(category.id)
        if product_count > 0:
            raise CategoryInUseError(
                f"Category {category.id} still has {product_count} product(s)"
            )
        await self.categories.delete(category)
        invalidate_categories_cache()

    # --- subcategories ---------------------------------------------------------

    async def list_subcategories(
        self,
        category_id: int,
        *,
        active_only: bool = False,
    ) -> list[Subcategory]:
        return await self.subcategories.list_by_category(
            category_id, active_only=active_only
        )

    async def list_subcategories_with_counts(
        self,
        category_id: int,
    ) -> list[tuple[Subcategory, int]]:
        """``(subcategory, product_count)`` in a single query."""
        return await self.subcategories.list_with_counts(category_id)

    async def get_subcategory(self, subcategory_id: int) -> Subcategory | None:
        return await self.subcategories.get_by_id(subcategory_id)

    async def create_subcategory(
        self,
        *,
        category_id: int,
        name: str,
        name_ru: str | None = None,
        name_en: str | None = None,
        name_de: str | None = None,
        name_uk: str | None = None,
        is_active: bool = True,
    ) -> Subcategory:
        return await self.subcategories.create_subcategory(
            category_id=category_id,
            name=name,
            name_ru=name_ru,
            name_en=name_en,
            name_de=name_de,
            name_uk=name_uk,
            is_active=is_active,
        )

    async def rename_subcategory(
        self,
        subcategory: Subcategory,
        name: str,
    ) -> Subcategory:
        return await self.subcategories.rename(subcategory, name)

    async def set_subcategory_names(
        self,
        subcategory: Subcategory,
        **names: str,
    ) -> Subcategory:
        return await self.subcategories.set_names(subcategory, **names)

    async def set_subcategory_active(
        self,
        subcategory: Subcategory,
        is_active: bool,
    ) -> Subcategory:
        return await self.subcategories.set_active(subcategory, is_active)

    async def move_subcategory(
        self,
        category_id: int,
        subcategory_id: int,
        *,
        direction: int,
    ) -> list[Subcategory]:
        return await self.subcategories.move(
            category_id, subcategory_id, direction=direction
        )

    async def reassign_subcategory(
        self,
        subcategory: Subcategory,
        category_id: int,
    ) -> Subcategory:
        return await self.subcategories.move_to_category(subcategory, category_id)

    async def count_subcategory_products(self, subcategory_id: int) -> int:
        return await self.subcategories.count_products(subcategory_id)

    async def delete_subcategory(self, subcategory: Subcategory) -> None:
        """Refuse while the brand still holds products."""
        product_count = await self.subcategories.count_products(subcategory.id)
        if product_count > 0:
            raise SubcategoryInUseError(
                f"Subcategory {subcategory.id} still has {product_count} product(s)"
            )
        await self.subcategories.delete(subcategory)

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

    async def list_products_with_parents(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Product]:
        """Admin listing with category and subcategory eagerly loaded."""
        return await self.products.list_with_parents(offset=offset, limit=limit)

    async def move_product_to_subcategory(
        self,
        product: Product,
        subcategory_id: int,
    ) -> Product:
        return await self.products.move_to_subcategory(product, subcategory_id)

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
        subcategory_id: int | None = None,
        name_uk: str | None = None,
        description_uk: str | None = None,
        image_file_id: str | None = None,
        is_active: bool = True,
    ) -> Product:
        return await self.products.create_product(
            category_id=category_id,
            subcategory_id=subcategory_id,
            name_uk=name_uk,
            description_uk=description_uk,
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
