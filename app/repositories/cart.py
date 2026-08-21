"""Cart repository."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import Cart, CartItem
from app.repositories.base import BaseRepository


class CartRepository(BaseRepository[Cart]):
    model = Cart

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_user_id(self, user_id: int) -> Cart | None:
        result = await self.session.scalars(select(Cart).where(Cart.user_id == user_id))
        return result.first()

    async def get_by_user_id_with_items(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> Cart | None:
        stmt = (
            select(Cart)
            .where(Cart.user_id == user_id)
            .options(
                selectinload(Cart.items).selectinload(CartItem.product),
            )
        )
        if for_update:
            # Lock the cart row so concurrent checkouts serialize in PostgreSQL.
            stmt = stmt.with_for_update(of=Cart)
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_with_items(self, cart_id: int) -> Cart | None:
        result = await self.session.scalars(
            select(Cart)
            .where(Cart.id == cart_id)
            .options(
                selectinload(Cart.items).selectinload(CartItem.product),
            )
        )
        return result.first()

    async def get_or_create_for_user(self, user_id: int) -> tuple[Cart, bool]:
        """Return (cart, created) for the given user."""
        cart = await self.get_by_user_id(user_id)
        if cart is not None:
            return cart, False
        try:
            async with self.session.begin_nested():
                cart = await self.create_and_add(user_id=user_id)
            return cart, True
        except IntegrityError:
            cart = await self.get_by_user_id(user_id)
            if cart is None:
                raise
            return cart, False

    async def clear(self, cart: Cart) -> Cart:
        """Remove all items from the cart."""
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await self.session.flush()
        await self.session.refresh(cart, attribute_names=["items"])
        return cart

    async def delete_by_user_id(self, user_id: int) -> bool:
        cart = await self.get_by_user_id(user_id)
        if cart is None:
            return False
        await self.delete(cart)
        return True
