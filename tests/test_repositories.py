"""Repository layer tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.repositories.cart import CartRepository
from app.repositories.category import CategoryRepository
from app.repositories.order import OrderRepository
from app.repositories.product import ProductRepository
from app.repositories.user import UserRepository
from tests.factories import (
    add_order_item,
    make_cart_with_item,
    make_category,
    make_order,
    make_product,
    make_user,
)


@pytest.mark.asyncio
async def test_user_get_or_create_by_telegram(session: AsyncSession) -> None:
    repo = UserRepository(session)
    user, created = await repo.get_or_create_by_telegram(
        555,
        username="alice",
        first_name="Alice",
    )
    assert created is True
    assert user.telegram_id == 555

    same, created_again = await repo.get_or_create_by_telegram(555, username="alice2")
    assert created_again is False
    assert same.id == user.id


@pytest.mark.asyncio
async def test_category_list_ordered_and_reorder(session: AsyncSession) -> None:
    repo = CategoryRepository(session)
    a = await make_category(session, name="A", sort_order=2)
    b = await make_category(session, name="B", sort_order=1)
    c = await make_category(session, name="C", sort_order=0)

    ordered = await repo.list_ordered()
    assert [item.name for item in ordered] == ["C", "B", "A"]

    await repo.reorder([a.id, b.id, c.id])
    reordered = await repo.list_ordered()
    assert [item.id for item in reordered] == [a.id, b.id, c.id]
    assert [item.sort_order for item in reordered] == [0, 1, 2]


@pytest.mark.asyncio
async def test_category_move_up_down(session: AsyncSession) -> None:
    repo = CategoryRepository(session)
    first = await make_category(session, name="First", sort_order=0)
    second = await make_category(session, name="Second", sort_order=1)

    moved = await repo.move(second.id, direction=-1)
    assert [item.id for item in moved] == [second.id, first.id]

    unchanged = await repo.move(second.id, direction=-1)
    assert [item.id for item in unchanged] == [second.id, first.id]


@pytest.mark.asyncio
async def test_product_list_by_category_active_only(
    session: AsyncSession,
) -> None:
    category = await make_category(session)
    active = await make_product(session, category, name_en="Active", is_active=True)
    await make_product(session, category, name_en="Hidden", is_active=False)

    repo = ProductRepository(session)
    products = await repo.list_by_category(category.id, active_only=True)
    assert [p.id for p in products] == [active.id]

    found = await repo.get_active_by_id(active.id)
    assert found is not None
    missing = await repo.get_active_by_id(
        (await make_product(session, category, is_active=False)).id
    )
    assert missing is None


@pytest.mark.asyncio
async def test_cart_get_with_items_and_clear(session: AsyncSession) -> None:
    user = await make_user(session)
    category = await make_category(session)
    product = await make_product(session, category, price="9.99")
    cart, _item = await make_cart_with_item(session, user, product, quantity=2)

    repo = CartRepository(session)
    loaded = await repo.get_by_user_id_with_items(user.id)
    assert loaded is not None
    assert loaded.id == cart.id
    assert len(loaded.items) == 1
    assert loaded.items[0].product is not None
    assert loaded.items[0].product.price == Decimal("9.99")

    await repo.clear(cart)
    emptied = await repo.get_by_user_id_with_items(user.id)
    assert emptied is not None
    assert emptied.items == []


@pytest.mark.asyncio
async def test_order_list_by_status_and_search(session: AsyncSession) -> None:
    user = await make_user(session)
    category = await make_category(session)
    product = await make_product(session, category)
    new_order = await make_order(
        session,
        user,
        status=OrderStatus.NEW,
        customer_name="Bob Smith",
        phone="+49111222333",
    )
    await add_order_item(session, new_order, product)
    await make_order(session, user, status=OrderStatus.COMPLETED, customer_name="Other")

    repo = OrderRepository(session)
    news = await repo.list_by_status(OrderStatus.NEW)
    assert len(news) == 1
    assert news[0].id == new_order.id
    assert await repo.count_by_status(OrderStatus.NEW) == 1

    by_id = await repo.search(str(new_order.id))
    assert by_id[0].id == new_order.id

    by_phone = await repo.search("111222")
    assert any(o.id == new_order.id for o in by_phone)

    by_name = await repo.search("Bob")
    assert any(o.id == new_order.id for o in by_name)
