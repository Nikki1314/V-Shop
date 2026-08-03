"""Cart service — add, update quantities, remove, totals (DB-backed)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.repositories.cart import CartRepository
from app.repositories.cart_item import CartItemRepository
from app.repositories.product import ProductRepository
from app.utils.product_display import localized_product_name


@dataclass(slots=True, frozen=True)
class CartLineView:
    item_id: int
    product_id: int
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


@dataclass(slots=True, frozen=True)
class CartView:
    cart_id: int
    lines: list[CartLineView]
    total: Decimal

    @property
    def is_empty(self) -> bool:
        return not self.lines


class CartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.carts = CartRepository(session)
        self.cart_items = CartItemRepository(session)
        self.products = ProductRepository(session)

    async def get_or_create_cart(self, user_id: int) -> Cart:
        cart, _created = await self.carts.get_or_create_for_user(user_id)
        return cart

    async def get_cart_with_items(self, user_id: int) -> Cart | None:
        return await self.carts.get_by_user_id_with_items(user_id)

    async def add_product(
        self,
        user_id: int,
        product: Product,
        quantity: int = 1,
    ) -> CartItem:
        """Add an active product to the user's cart (or increase quantity)."""
        if quantity < 1:
            raise ValueError("quantity must be >= 1")
        if not product.is_active:
            raise ValueError("Product is inactive")
        cart = await self.get_or_create_cart(user_id)
        return await self.cart_items.add_item(cart.id, product.id, quantity=quantity)

    async def increase_item(self, user_id: int, item_id: int, step: int = 1) -> bool:
        """Increase quantity. Returns False if the item is missing or not owned."""
        item = await self.cart_items.get_by_id_for_user(item_id, user_id)
        if item is None:
            return False
        await self.cart_items.increment(item, step=step)
        return True

    async def decrease_item(self, user_id: int, item_id: int, step: int = 1) -> bool:
        """Decrease quantity (removes row at 0). Returns False if missing/not owned."""
        item = await self.cart_items.get_by_id_for_user(item_id, user_id)
        if item is None:
            return False
        await self.cart_items.decrement(item, step=step)
        return True

    async def remove_item(self, user_id: int, item_id: int) -> bool:
        item = await self.cart_items.get_by_id_for_user(item_id, user_id)
        if item is None:
            return False
        await self.cart_items.delete(item)
        return True

    async def clear(self, user_id: int) -> bool:
        cart = await self.carts.get_by_user_id(user_id)
        if cart is None:
            return False
        await self.carts.clear(cart)
        return True

    @staticmethod
    def calculate_total(items: list[CartItem]) -> Decimal:
        total = Decimal("0")
        for item in items:
            if item.product is None:
                continue
            total += Decimal(item.product.price) * item.quantity
        return total

    async def get_view(self, user_id: int, *, language: str) -> CartView | None:
        """Build a localized cart snapshot with line totals and grand total."""
        cart = await self.get_cart_with_items(user_id)
        if cart is None:
            return None

        lines: list[CartLineView] = []
        for item in sorted(cart.items, key=lambda row: row.id):
            product = item.product
            if product is None:
                continue
            unit = Decimal(product.price)
            lines.append(
                CartLineView(
                    item_id=item.id,
                    product_id=product.id,
                    name=localized_product_name(product, language),
                    quantity=item.quantity,
                    unit_price=unit,
                    line_total=unit * item.quantity,
                )
            )

        return CartView(
            cart_id=cart.id,
            lines=lines,
            total=sum((line.line_total for line in lines), Decimal("0")),
        )
