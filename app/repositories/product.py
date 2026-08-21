"""Product repository."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.repositories.base import BaseRepository
from app.repositories.visibility import only_sellable_products


class ProductRepository(BaseRepository[Product]):
    model = Product

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_with_category(self, product_id: int) -> Product | None:
        result = await self.session.scalars(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.subcategory),
            )
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
            select(func.count()).select_from(OrderItem).where(OrderItem.product_id == product_id)
        )
        return int(result or 0)

    async def list_by_subcategory(
        self,
        subcategory_id: int,
        *,
        active_only: bool = True,
    ) -> list[Product]:
        stmt = select(Product).where(Product.subcategory_id == subcategory_id)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        result = await self.session.scalars(stmt.order_by(Product.id.asc()))
        return list(result.all())

    async def list_visible_by_subcategory(self, subcategory_id: int) -> list[Product]:
        """
        Customer-visible products in a brand.

        Joins both parents: an active product under a deactivated brand — or a
        deactivated category — must not reach a customer.
        """
        result = await self.session.scalars(
            select(Product)
            .join(Subcategory, Subcategory.id == Product.subcategory_id)
            .join(Category, Category.id == Subcategory.category_id)
            .where(
                Product.subcategory_id == subcategory_id,
                Product.is_active.is_(True),
                Subcategory.is_active.is_(True),
                Category.is_active.is_(True),
            )
            .order_by(Product.id.asc())
        )
        return list(result.all())

    async def get_visible_by_id(self, product_id: int) -> Product | None:
        """A product a customer may open: active all the way up the hierarchy."""
        result = await self.session.scalars(
            select(Product)
            .join(Subcategory, Subcategory.id == Product.subcategory_id)
            .join(Category, Category.id == Subcategory.category_id)
            .where(
                Product.id == product_id,
                Product.is_active.is_(True),
                Subcategory.is_active.is_(True),
                Category.is_active.is_(True),
            )
            .options(selectinload(Product.subcategory))
        )
        return result.first()

    async def list_unsellable_ids(self, product_ids: list[int]) -> set[int]:
        """
        Of the given products, which must not be sold.

        Expressed as the complement of :func:`only_sellable_products` rather than
        as its own negated condition, so this checkout guard and the statistics
        rankings can never disagree about what "on sale" means. Asserted over the
        full state matrix by ``tests/test_visibility.py``.
        One query, never N+1.
        """
        if not product_ids:
            return set()
        rows = await self.session.scalars(
            only_sellable_products(select(Product.id)).where(Product.id.in_(product_ids))
        )
        # An id that matches no row at all — a product deleted between adding it
        # to the cart and checking out — is absent from `sellable` and therefore
        # reported unsellable, which is the safe answer.
        return set(product_ids) - set(rows.all())

    async def list_with_parents(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Product]:
        """Admin listing with both parents eagerly loaded (no N+1 on render)."""
        stmt = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.subcategory).selectinload(Subcategory.category),
            )
            .order_by(Product.id.asc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def move_to_subcategory(self, product: Product, subcategory_id: int) -> Product:
        """Reassign a product to another brand, keeping the legacy link in step."""
        subcategory = await self.session.get(Subcategory, subcategory_id)
        if subcategory is None:
            raise ValueError(f"Subcategory {subcategory_id} does not exist")
        return await self.update(
            product,
            subcategory_id=subcategory_id,
            category_id=subcategory.category_id,
        )

    async def count_by_subcategory(self, subcategory_id: int) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.subcategory_id == subcategory_id)
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
        subcategory_id: int | None = None,
        name_uk: str | None = None,
        description_uk: str | None = None,
        image_file_id: str | None = None,
        is_active: bool = True,
    ) -> Product:
        """
        Create a product.

        Ukrainian fields fall back to the Russian text when not supplied, so
        callers that predate the four-language catalog keep working and never
        write NULLs. Those fallbacks are placeholders for admin review.
        """
        return await self.create_and_add(
            subcategory_id=subcategory_id,
            category_id=category_id,
            name_ru=name_ru,
            name_en=name_en,
            name_de=name_de,
            name_uk=name_uk or name_ru,
            description_ru=description_ru,
            description_en=description_en,
            description_de=description_de,
            description_uk=description_uk or description_ru,
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
