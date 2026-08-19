"""Catalog service — the customer-facing view of the catalog.

Everything this service returns is customer-visible: inactive categories,
subcategories and products are filtered out, and visibility cascades down the
hierarchy. An active product inside a deactivated brand is NOT visible, and
neither is an active brand inside a deactivated category — the repository
queries join upwards so that rule cannot be bypassed by calling one level
directly. Admin views use :class:`app.services.admin.catalog.AdminCatalogService`,
which deliberately shows everything.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.repositories.category import CategoryRepository
from app.repositories.product import ProductRepository
from app.repositories.subcategory import SubcategoryRepository
from app.utils.cache import categories_list_cache


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.categories = CategoryRepository(session)
        self.subcategories = SubcategoryRepository(session)
        self.products = ProductRepository(session)

    # --- level 1: categories ---------------------------------------------------

    async def list_categories(self) -> list[Category]:
        """
        Active categories in display order, TTL-cached.

        The instances are NOT expunged. Expunging detached the session's own
        identity-mapped objects, so a caller that later mutated the same
        ``Category`` (e.g. deactivating it) had its write silently dropped —
        ``flush()`` ignores detached instances. Cached entries are read-only
        snapshots used to build keyboards; their column values stay readable
        after the originating session closes because the session factory sets
        ``expire_on_commit=False``.
        """
        cached = categories_list_cache.get()
        if cached is not None:
            return cached

        categories = await self.categories.list_ordered(active_only=True)
        categories_list_cache.set(categories)
        return categories

    async def get_category(self, category_id: int) -> Category | None:
        """Only returns the category when it is visible to customers."""
        return await self.categories.get_active_by_id(category_id)

    # --- level 2: subcategories / brands ---------------------------------------

    async def list_subcategories(self, category_id: int) -> list[Subcategory]:
        """Active brands within an active category."""
        return await self.subcategories.list_visible_by_category(category_id)

    async def get_subcategory(self, subcategory_id: int) -> Subcategory | None:
        return await self.subcategories.get_visible_by_id(subcategory_id)

    async def get_category_with_subcategories(
        self,
        category_id: int,
    ) -> tuple[Category | None, list[Subcategory]]:
        """Open a category: the category itself plus its visible brands."""
        category = await self.get_category(category_id)
        if category is None:
            return None, []
        return category, await self.list_subcategories(category_id)

    # --- level 3: products -----------------------------------------------------

    async def list_subcategory_products(self, subcategory_id: int) -> list[Product]:
        """Active products in an active brand under an active category."""
        return await self.products.list_visible_by_subcategory(subcategory_id)

    async def get_subcategory_with_products(
        self,
        subcategory_id: int,
    ) -> tuple[Subcategory | None, list[Product]]:
        """Open a brand: the brand itself plus its visible products."""
        subcategory = await self.get_subcategory(subcategory_id)
        if subcategory is None:
            return None, []
        return subcategory, await self.list_subcategory_products(subcategory_id)

    async def get_product(self, product_id: int) -> Product | None:
        """A product the customer may open, checked up the whole hierarchy."""
        return await self.products.get_visible_by_id(product_id)

    # --- pre-hierarchy API (still used by the current catalog UI) --------------

    async def list_products(self, category_id: int) -> list[Product]:
        """Active products linked directly to a category (legacy flat view)."""
        return await self.products.list_by_category(category_id, active_only=True)

    async def get_category_with_products(
        self,
        category_id: int,
    ) -> tuple[Category | None, list[Product]]:
        """Legacy flat view: category plus its active products."""
        category = await self.get_category(category_id)
        if category is None:
            return None, []
        return category, await self.list_products(category_id)

    async def get_active_product(self, product_id: int) -> Product | None:
        """Legacy lookup: checks the product only, not its parents."""
        return await self.products.get_active_by_id(product_id)

    async def get_purchasable_product(self, product_id: int) -> Product | None:
        """
        A product the customer may actually put in the cart.

        Products that sit in the hierarchy must be visible all the way up, so a
        stale card cannot add an item from a hidden brand. Pre-hierarchy rows
        carry no brand and would fail that join, so they fall back to their own
        ``is_active`` flag — otherwise existing products would become unbuyable.
        """
        product = await self.products.get_visible_by_id(product_id)
        if product is not None:
            return product
        legacy = await self.products.get_active_by_id(product_id)
        if legacy is not None and legacy.subcategory_id is None:
            return legacy
        return None
