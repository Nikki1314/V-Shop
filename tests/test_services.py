"""Service layer tests (cart, catalog, user)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CityChoice, LanguageCode
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.user import UserService
from app.utils.cache import invalidate_categories_cache
from tests.factories import make_cart_with_item, make_category, make_product, make_user


@pytest.fixture(autouse=True)
def _clear_category_cache() -> None:
    invalidate_categories_cache()
    yield
    invalidate_categories_cache()


@pytest.mark.asyncio
async def test_cart_add_increase_decrease_remove(session: AsyncSession) -> None:
    user = await make_user(session)
    category = await make_category(session)
    product = await make_product(session, category, price="5.00")
    cart_svc = CartService(session)

    item = await cart_svc.add_product(user.id, product, quantity=1)
    assert item.quantity == 1

    await cart_svc.add_product(user.id, product, quantity=2)
    view = await cart_svc.get_view(user.id, language="en")
    assert view is not None
    assert len(view.lines) == 1
    assert view.lines[0].quantity == 3
    assert view.total == Decimal("15.00")

    assert await cart_svc.increase_item(user.id, item.id) is True
    view = await cart_svc.get_view(user.id, language="en")
    assert view is not None
    assert view.lines[0].quantity == 4

    assert await cart_svc.decrease_item(user.id, item.id, step=3) is True
    view = await cart_svc.get_view(user.id, language="en")
    assert view is not None
    assert view.lines[0].quantity == 1

    assert await cart_svc.remove_item(user.id, item.id) is True
    view = await cart_svc.get_view(user.id, language="en")
    assert view is not None
    assert view.is_empty


@pytest.mark.asyncio
async def test_cart_rejects_inactive_product(session: AsyncSession) -> None:
    user = await make_user(session)
    category = await make_category(session)
    product = await make_product(session, category, is_active=False)
    with pytest.raises(ValueError, match="inactive"):
        await CartService(session).add_product(user.id, product)


@pytest.mark.asyncio
async def test_cart_item_ownership_guard(session: AsyncSession) -> None:
    owner = await make_user(session, telegram_id=1)
    other = await make_user(session, telegram_id=2)
    category = await make_category(session)
    product = await make_product(session, category)
    _cart, item = await make_cart_with_item(session, owner, product)

    cart_svc = CartService(session)
    assert await cart_svc.increase_item(other.id, item.id) is False
    assert await cart_svc.remove_item(other.id, item.id) is False


@pytest.mark.asyncio
async def test_catalog_lists_active_products_only(session: AsyncSession) -> None:
    category = await make_category(session, name="Cats")
    active = await make_product(session, category, name_en="On", is_active=True)
    await make_product(session, category, name_en="Off", is_active=False)

    catalog = CatalogService(session)
    categories = await catalog.list_categories()
    assert any(c.id == category.id for c in categories)

    products = await catalog.list_products(category.id)
    assert [p.id for p in products] == [active.id]

    found, listed = await catalog.get_category_with_products(category.id)
    assert found is not None
    assert found.id == category.id
    assert [p.id for p in listed] == [active.id]


@pytest.mark.asyncio
async def test_user_ensure_and_onboarding_flags(session: AsyncSession) -> None:
    tg = SimpleNamespace(id=7777, username="neo", first_name="Neo")
    service = UserService(session)

    user = await service.ensure_user(tg)  # type: ignore[arg-type]
    assert user.telegram_id == 7777
    assert UserService.needs_language(user) is True
    assert UserService.needs_city(user) is True
    assert UserService.is_onboarded(user) is False

    await service.save_language(user, LanguageCode.DE)
    await service.save_city(user, CityChoice.DELIVERY)
    assert UserService.is_onboarded(user) is True

    again = await service.ensure_user(tg)  # type: ignore[arg-type]
    assert again.id == user.id
    assert again.language == LanguageCode.DE
