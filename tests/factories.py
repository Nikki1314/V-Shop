"""Test data helpers."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cart import Cart, CartItem
from app.models.category import Category
from app.models.enums import CityChoice, LanguageCode, OrderStatus
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.user import User


async def make_user(
    session: AsyncSession,
    *,
    telegram_id: int = 2001,
    language: LanguageCode = LanguageCode.EN,
    city: CityChoice | None = CityChoice.BERLIN,
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=f"user{telegram_id}",
        first_name="Test",
        language=language,
        selected_city=city,
    )
    session.add(user)
    await session.flush()
    return user


async def make_category(
    session: AsyncSession,
    *,
    name: str = "Category",
    sort_order: int = 0,
) -> Category:
    category = Category(name=name, sort_order=sort_order)
    session.add(category)
    await session.flush()
    return category


async def make_product(
    session: AsyncSession,
    category: Category,
    *,
    name_en: str = "Product",
    price: str | Decimal = "10.00",
    is_active: bool = True,
) -> Product:
    product = Product(
        category_id=category.id,
        name_ru=name_en,
        name_en=name_en,
        name_de=name_en,
        description_ru="d",
        description_en="d",
        description_de="d",
        flavor="flavor",
        volume="30ml",
        nicotine_strength="0mg",
        price=Decimal(str(price)),
        is_active=is_active,
    )
    session.add(product)
    await session.flush()
    return product


async def make_cart_with_item(
    session: AsyncSession,
    user: User,
    product: Product,
    *,
    quantity: int = 1,
) -> tuple[Cart, CartItem]:
    cart = Cart(user_id=user.id)
    session.add(cart)
    await session.flush()
    item = CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity)
    session.add(item)
    await session.flush()
    return cart, item


async def make_order(
    session: AsyncSession,
    user: User,
    *,
    status: OrderStatus = OrderStatus.NEW,
    customer_name: str = "Alice",
    phone: str | None = "+49123456789",
) -> Order:
    order = Order(
        user_id=user.id,
        customer_name=customer_name,
        city=CityChoice.BERLIN.value,
        delivery_type="pickup",
        address="Street 1",
        preferred_time="ASAP",
        phone=phone,
        total_price=Decimal("10.00"),
        status=status,
    )
    session.add(order)
    await session.flush()
    return order


async def add_order_item(
    session: AsyncSession,
    order: Order,
    product: Product,
    *,
    quantity: int = 1,
    price: str | Decimal | None = None,
) -> OrderItem:
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        price=Decimal(str(price if price is not None else product.price)),
    )
    session.add(item)
    await session.flush()
    return item
