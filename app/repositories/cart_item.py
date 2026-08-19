"""CartItem repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import Cart, CartItem
from app.repositories.base import BaseRepository

MAX_CART_ITEM_QUANTITY = 99


class CartItemRepository(BaseRepository[CartItem]):
    model = CartItem

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_cart_and_product(
        self,
        cart_id: int,
        product_id: int,
    ) -> CartItem | None:
        result = await self.session.scalars(
            select(CartItem).where(
                CartItem.cart_id == cart_id,
                CartItem.product_id == product_id,
            )
        )
        return result.first()

    async def get_by_id_for_user(self, item_id: int, user_id: int) -> CartItem | None:
        """Load a cart line only if it belongs to the given user."""
        result = await self.session.scalars(
            select(CartItem)
            .join(Cart, CartItem.cart_id == Cart.id)
            .where(CartItem.id == item_id, Cart.user_id == user_id)
        )
        return result.first()

    async def list_by_cart(
        self,
        cart_id: int,
        *,
        with_product: bool = True,
    ) -> list[CartItem]:
        stmt = select(CartItem).where(CartItem.cart_id == cart_id).order_by(CartItem.id.asc())
        if with_product:
            stmt = stmt.options(selectinload(CartItem.product))
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def add_item(
        self,
        cart_id: int,
        product_id: int,
        quantity: int = 1,
    ) -> CartItem:
        """Add a product to the cart or increase quantity if it already exists."""
        if quantity < 1:
            raise ValueError("quantity must be >= 1")

        existing = await self.get_by_cart_and_product(cart_id, product_id)
        if existing is not None:
            new_qty = min(existing.quantity + quantity, MAX_CART_ITEM_QUANTITY)
            return await self.update(existing, quantity=new_qty)

        try:
            async with self.session.begin_nested():
                return await self.create_and_add(
                    cart_id=cart_id,
                    product_id=product_id,
                    quantity=min(quantity, MAX_CART_ITEM_QUANTITY),
                )
        except IntegrityError:
            # A rapid second tap inserted the same line between our SELECT and
            # INSERT; uq_cart_product rejected ours. Fall back to incrementing
            # the row that won, so the customer sees quantity 2, not an error.
            existing = await self.get_by_cart_and_product(cart_id, product_id)
            if existing is None:
                raise
            new_qty = min(existing.quantity + quantity, MAX_CART_ITEM_QUANTITY)
            return await self.update(existing, quantity=new_qty)

    async def set_quantity(self, item: CartItem, quantity: int) -> CartItem | None:
        """Set absolute quantity. Deletes the row when quantity drops below 1."""
        if quantity < 1:
            await self.delete(item)
            return None
        capped = min(quantity, MAX_CART_ITEM_QUANTITY)
        return await self.update(item, quantity=capped)

    async def increment(self, item: CartItem, step: int = 1) -> CartItem:
        if step < 1:
            raise ValueError("step must be >= 1")
        new_qty = min(item.quantity + step, MAX_CART_ITEM_QUANTITY)
        return await self.update(item, quantity=new_qty)

    async def decrement(self, item: CartItem, step: int = 1) -> CartItem | None:
        if step < 1:
            raise ValueError("step must be >= 1")
        return await self.set_quantity(item, item.quantity - step)

    async def remove_product(self, cart_id: int, product_id: int) -> bool:
        item = await self.get_by_cart_and_product(cart_id, product_id)
        if item is None:
            return False
        await self.delete(item)
        return True
