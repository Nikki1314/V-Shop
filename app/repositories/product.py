"""Product repository."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    model = Product

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_with_category(self, product_id: int) -> Product | None:
        result = await self.session.scalars(
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.category))
        )
        return result.first()

    async def get_active_by_id(self, product_id: int) -> Product | None:
        result = await self.session.scalars(
            select(Product).where(
                Product.id == product_id,
                Product.is_active.is_(True),
            )
        )
        return result.first()

    async def list_by_category(
        self,
        category_id: int,
        *,
        active_only: bool = True,
    ) -> list[Product]:
        stmt = select(Product).where(Product.category_id == category_id)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        result = await self.session.scalars(stmt.order_by(Product.id.asc()))
        return list(result.all())

    async def list_active(self, *, offset: int = 0, limit: int | None = None) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.is_active.is_(True))
            .order_by(Product.id.asc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def list_all_admin(self, *, offset: int = 0, limit: int | None = None) -> list[Product]:
        """List all products including inactive (admin views)."""
        stmt = (
            select(Product)
            .options(selectinload(Product.category))
            .order_by(Product.id.asc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_all(self) -> int:
        result = await self.session.scalar(select(func.count()).select_from(Product))
        return int(result or 0)

    async def count_order_references(self, product_id: int) -> int:
        from app.models.order import OrderItem

        result = await self.session.scalar(
            select(func.count())
            .select_from(OrderItem)
            .where(OrderItem.product_id == product_id)
        )
        return int(result or 0)

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
        return await self.create_and_add(
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
            price=Decimal(str(price)),
            image_file_id=image_file_id,
            is_active=is_active,
        )

    async def update_product(self, product: Product, **fields: Any) -> Product:
        if "price" in fields and fields["price"] is not None:
            fields["price"] = Decimal(str(fields["price"]))
        return await self.update(product, **fields)

    async def enable(self, product: Product) -> Product:
        return await self.update(product, is_active=True)

    async def disable(self, product: Product) -> Product:
        return await self.update(product, is_active=False)

    async def set_active(self, product: Product, is_active: bool) -> Product:
        return await self.update(product, is_active=is_active)
