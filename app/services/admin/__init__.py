"""Admin façade — composes catalog, order, and user admin services."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.product import Product
from app.services.admin.catalog import AdminCatalogService
from app.services.admin.exceptions import CategoryInUseError, ProductInUseError
from app.services.admin.orders import AdminOrderService
from app.services.admin.users import AdminUserService

__all__ = [
    "AdminService",
    "AdminCatalogService",
    "AdminOrderService",
    "AdminUserService",
    "CategoryInUseError",
    "ProductInUseError",
]


class AdminService:
    """
    Backward-compatible façade over focused admin services.

    Prefer injecting ``AdminCatalogService`` / ``AdminOrderService`` /
    ``AdminUserService`` in new code; existing handlers may keep using this type.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = AdminCatalogService(session)
        self.order_admin = AdminOrderService(session)
        self.user_admin = AdminUserService(session)
        # Preserve legacy repository attributes used by some call sites.
        self.products = self.catalog.products
        self.categories = self.catalog.categories
        self.orders = self.order_admin.orders
        self.order_items = self.order_admin.order_items
        self.users = self.user_admin.users

    # --- categories / products ---
    async def list_categories(self) -> list[Category]:
        return await self.catalog.list_categories()

    async def get_category(self, category_id: int) -> Category | None:
        return await self.catalog.get_category(category_id)

    async def get_category_by_name(self, name: str) -> Category | None:
        return await self.catalog.get_category_by_name(name)

    async def create_category(self, name: str) -> Category:
        return await self.catalog.create_category(name)

    async def rename_category(self, category: Category, name: str) -> Category:
        return await self.catalog.rename_category(category, name)

    async def delete_category(self, category: Category) -> None:
        await self.catalog.delete_category(category)

    async def move_category(self, category_id: int, *, direction: int) -> list[Category]:
        return await self.catalog.move_category(category_id, direction=direction)

    async def count_category_products(self, category_id: int) -> int:
        return await self.catalog.count_category_products(category_id)

    async def list_products(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Product]:
        return await self.catalog.list_products(offset=offset, limit=limit)

    async def count_products(self) -> int:
        return await self.catalog.count_products()

    async def page_products(
        self,
        *,
        offset: int = 0,
        limit: int,
    ) -> tuple[int, list[Product]]:
        return await self.catalog.page_products(offset=offset, limit=limit)

    async def get_product(self, product_id: int) -> Product | None:
        return await self.catalog.get_product(product_id)

    async def create_product(self, **kwargs: Any) -> Product:
        return await self.catalog.create_product(**kwargs)

    async def update_product(self, product: Product, **fields: Any) -> Product:
        return await self.catalog.update_product(product, **fields)

    async def set_product_price(self, product: Product, price: Decimal | str | float) -> Product:
        return await self.catalog.set_product_price(product, price)

    async def set_product_descriptions(
        self,
        product: Product,
        *,
        description_ru: str,
        description_en: str,
        description_de: str,
    ) -> Product:
        return await self.catalog.set_product_descriptions(
            product,
            description_ru=description_ru,
            description_en=description_en,
            description_de=description_de,
        )

    async def enable_product(self, product: Product) -> Product:
        return await self.catalog.enable_product(product)

    async def disable_product(self, product: Product) -> Product:
        return await self.catalog.disable_product(product)

    async def delete_product(self, product: Product) -> None:
        await self.catalog.delete_product(product)

    # --- orders ---
    async def list_orders_by_status(
        self,
        status: OrderStatus,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Order]:
        return await self.order_admin.list_orders_by_status(
            status, offset=offset, limit=limit
        )

    async def count_orders_by_status(self, status: OrderStatus) -> int:
        return await self.order_admin.count_orders_by_status(status)

    async def page_orders_by_status(
        self,
        status: OrderStatus,
        *,
        offset: int = 0,
        limit: int,
    ) -> tuple[int, list[Order]]:
        return await self.order_admin.page_orders_by_status(
            status, offset=offset, limit=limit
        )

    async def get_order(self, order_id: int) -> Order | None:
        return await self.order_admin.get_order(order_id)

    async def search_orders(self, query: str, *, limit: int = 20) -> list[Order]:
        return await self.order_admin.search_orders(query, limit=limit)

    async def set_order_status(self, order: Order, status: OrderStatus) -> Order:
        return await self.order_admin.set_order_status(order, status)

    # --- users / broadcast ---
    async def list_broadcast_recipient_ids(self) -> list[int]:
        return await self.user_admin.list_broadcast_recipient_ids()

    async def count_users(self) -> int:
        return await self.user_admin.count_users()
