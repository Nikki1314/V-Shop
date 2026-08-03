"""Admin service tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.services.admin import (
    AdminCatalogService,
    AdminOrderService,
    AdminService,
    AdminUserService,
    CategoryInUseError,
    ProductInUseError,
)
from app.utils.cache import invalidate_categories_cache
from tests.factories import (
    add_order_item,
    make_category,
    make_order,
    make_product,
    make_user,
)


@pytest.fixture(autouse=True)
def _clear_category_cache() -> None:
    invalidate_categories_cache()
    yield
    invalidate_categories_cache()


@pytest.mark.asyncio
async def test_admin_category_crud_and_in_use(session: AsyncSession) -> None:
    catalog = AdminCatalogService(session)
    created = await catalog.create_category("New Cat")
    assert created.name == "New Cat"
    assert created.sort_order >= 1

    renamed = await catalog.rename_category(created, "Renamed")
    assert renamed.name == "Renamed"

    product = await make_product(session, renamed)
    with pytest.raises(CategoryInUseError):
        await catalog.delete_category(renamed)

    # Delete product first, then category.
    await catalog.delete_product(product)
    await catalog.delete_category(renamed)
    assert await catalog.get_category(renamed.id) is None


@pytest.mark.asyncio
async def test_admin_category_move(session: AsyncSession) -> None:
    catalog = AdminCatalogService(session)
    first = await catalog.create_category("First")
    second = await catalog.create_category("Second")

    ordered = await catalog.move_category(second.id, direction=-1)
    assert [c.id for c in ordered[:2]] == [second.id, first.id]


@pytest.mark.asyncio
async def test_admin_product_lifecycle(session: AsyncSession) -> None:
    catalog = AdminCatalogService(session)
    category = await catalog.create_category("Liquids")

    product = await catalog.create_product(
        category_id=category.id,
        name_ru="Р",
        name_en="EN",
        name_de="DE",
        description_ru="dr",
        description_en="de",
        description_de="dd",
        flavor="Mint",
        volume="30ml",
        nicotine_strength="6mg",
        price="15.00",
        is_active=True,
    )
    assert product.is_active is True
    assert product.price == Decimal("15.00")

    product = await catalog.set_product_price(product, "20.50")
    assert product.price == Decimal("20.50")

    product = await catalog.set_product_descriptions(
        product,
        description_ru="ru2",
        description_en="en2",
        description_de="de2",
    )
    assert product.description_en == "en2"

    product = await catalog.disable_product(product)
    assert product.is_active is False
    product = await catalog.enable_product(product)
    assert product.is_active is True

    total, page = await catalog.page_products(offset=0, limit=10)
    assert total >= 1
    assert any(p.id == product.id for p in page)

    await catalog.delete_product(product)
    assert await catalog.get_product(product.id) is None


@pytest.mark.asyncio
async def test_admin_product_delete_blocked_by_orders(session: AsyncSession) -> None:
    catalog = AdminCatalogService(session)
    user = await make_user(session)
    category = await make_category(session)
    product = await make_product(session, category)
    order = await make_order(session, user)
    await add_order_item(session, order, product)

    with pytest.raises(ProductInUseError):
        await catalog.delete_product(product)


@pytest.mark.asyncio
async def test_admin_order_status_and_search(session: AsyncSession) -> None:
    orders = AdminOrderService(session)
    user = await make_user(session)
    order = await make_order(
        session,
        user,
        status=OrderStatus.NEW,
        customer_name="Searchable",
        phone="+49999888777",
    )

    updated = await orders.set_order_status(order, OrderStatus.ACCEPTED)
    assert updated.status == OrderStatus.ACCEPTED

    total, page = await orders.page_orders_by_status(
        OrderStatus.ACCEPTED,
        offset=0,
        limit=10,
    )
    assert total == 1
    assert page[0].id == order.id

    found = await orders.search_orders("Searchable")
    assert any(o.id == order.id for o in found)


@pytest.mark.asyncio
async def test_admin_user_broadcast_ids(session: AsyncSession) -> None:
    await make_user(session, telegram_id=101)
    await make_user(session, telegram_id=202)
    users = AdminUserService(session)

    ids = await users.list_broadcast_recipient_ids()
    assert set(ids) >= {101, 202}
    assert await users.count_users() >= 2


@pytest.mark.asyncio
async def test_admin_service_facade_delegates(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Facade Cat")
    assert await admin.get_category(category.id) is not None
    assert await admin.count_users() >= 0
