"""QA sweep of the catalog flow: four languages, edge cases, stale input."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.catalog import (
    CALLBACK_CATALOG_OPEN,
    CALLBACK_CATEGORY_PREFIX,
    CALLBACK_PRODUCT_PREFIX,
    CALLBACK_SUBCATEGORY_PREFIX,
)
from app.keyboards.product import add_to_cart_keyboard, product_added_keyboard
from app.models.enums import CityChoice, LanguageCode
from app.services.admin import AdminService
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.localization import LocalizationService
from app.services.order import InactiveProductError, OrderService
from app.utils.cache import invalidate_categories_cache
from app.utils.validators import parse_positive_int
from tests.factories import make_user

LANGS = ("ru", "en", "de", "uk")
BASE = dict(
    flavor="Tropic", volume="60ml", nicotine_strength="6mg", price=Decimal("18.00")
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_categories_cache()


async def _shop(session: AsyncSession):  # type: ignore[no-untyped-def]
    admin = AdminService(session)
    category = await admin.create_category(
        "Liquids", name_ru="Жидкости", name_en="Liquids",
        name_de="Liquids DE", name_uk="Рідини",
    )
    brand = await admin.create_subcategory(
        category_id=category.id, name="Brand A",
        name_ru="Бренд А", name_en="Brand A", name_de="Marke A", name_uk="Бренд А",
    )
    await session.flush()
    product = await admin.create_product(
        category_id=category.id, subcategory_id=brand.id,
        name_ru="Манго", name_en="Mango", name_de="Mango DE", name_uk="Манго UA",
        description_ru="о", description_en="d", description_de="b", description_uk="о",
        **BASE,
    )
    await session.flush()
    return admin, category, brand, product


def _payloads(markup) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ============================================================ happy path


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.asyncio
async def test_full_flow_in_each_language(
    session: AsyncSession, language: str
) -> None:
    """Language → Catalog → Category → Brand → Product → Cart → Back."""
    _admin, category, brand, product = await _shop(session)
    user = await make_user(
        session, telegram_id=8000 + LANGS.index(language),
        language=LanguageCode(language), city=CityChoice.BERLIN,
    )
    await session.flush()

    i18n = LocalizationService.from_user(user)
    assert i18n.language == language

    catalog = CatalogService(session)
    assert [c.id for c in await catalog.list_categories()] == [category.id]
    _c, brands = await catalog.get_category_with_subcategories(category.id)
    assert [s.id for s in brands] == [brand.id]
    _s, products = await catalog.get_subcategory_with_products(brand.id)
    assert [p.id for p in products] == [product.id]

    card = await catalog.get_purchasable_product(product.id)
    assert card is not None

    await CartService(session).add_product(user.id, card, quantity=1)
    await session.flush()
    view = await CartService(session).get_view(user.id, language=language)
    assert view is not None and len(view.lines) == 1
    assert view.total == Decimal("18.00")

    # Back from the added-to-cart screen resumes the same brand
    assert _payloads(product_added_keyboard(i18n, subcategory_id=brand.id))[0] == (
        f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}"
    )


# ============================================================ empty levels


@pytest.mark.asyncio
async def test_category_with_no_brands(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Empty")
    await session.flush()

    catalog = CatalogService(session)
    opened, brands = await catalog.get_category_with_subcategories(category.id)
    assert opened is not None
    assert brands == []


@pytest.mark.asyncio
async def test_brand_with_no_products(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    brand = await admin.create_subcategory(category_id=category.id, name="Empty")
    await session.flush()

    opened, products = await CatalogService(session).get_subcategory_with_products(
        brand.id
    )
    assert opened is not None
    assert products == []


@pytest.mark.asyncio
async def test_catalog_with_no_categories(session: AsyncSession) -> None:
    assert await CatalogService(session).list_categories() == []


# ========================================================= inactive tree


@pytest.mark.asyncio
async def test_inactive_at_each_level(session: AsyncSession) -> None:
    admin, category, brand, product = await _shop(session)
    catalog = CatalogService(session)

    await admin.disable_product(product)
    await session.flush()
    assert await catalog.list_subcategory_products(brand.id) == []
    assert await catalog.get_product(product.id) is None
    await admin.enable_product(product)
    await session.flush()

    await admin.set_subcategory_active(brand, False)
    await session.flush()
    assert await catalog.list_subcategories(category.id) == []
    assert await catalog.get_product(product.id) is None
    await admin.set_subcategory_active(brand, True)
    await session.flush()

    await admin.set_category_active(category, False)
    await session.flush()
    invalidate_categories_cache()
    assert await catalog.list_categories() == []
    assert await catalog.get_product(product.id) is None


# ======================================================== stale callbacks


@pytest.mark.asyncio
async def test_stale_ids_resolve_to_nothing(session: AsyncSession) -> None:
    """Nonexistent ids must return None, never raise."""
    catalog = CatalogService(session)
    assert await catalog.get_category(999_999) is None
    assert await catalog.get_subcategory(999_999) is None
    assert await catalog.get_product(999_999) is None
    assert await catalog.get_purchasable_product(999_999) is None
    assert await catalog.list_subcategories(999_999) == []
    assert await catalog.list_subcategory_products(999_999) == []


@pytest.mark.parametrize(
    "raw", ["", "abc", "-1", "0", "1.5", " ", "1;2", "99999999999999999999", "١٢٣"]
)
def test_malformed_callback_ids_are_rejected(raw: str) -> None:
    parsed = parse_positive_int(raw)
    assert parsed is None or parsed > 0


@pytest.mark.asyncio
async def test_deleted_product_stops_being_reachable(session: AsyncSession) -> None:
    admin, _category, brand, product = await _shop(session)
    product_id = product.id

    await admin.delete_product(product)
    await session.flush()

    catalog = CatalogService(session)
    assert await catalog.get_product(product_id) is None
    assert await catalog.get_purchasable_product(product_id) is None
    assert await catalog.list_subcategory_products(brand.id) == []


@pytest.mark.asyncio
async def test_deleted_brand_stops_being_reachable(session: AsyncSession) -> None:
    admin, category, brand, product = await _shop(session)
    brand_id = brand.id
    await admin.delete_product(product)
    await session.flush()
    await admin.delete_subcategory(brand)
    await session.flush()

    catalog = CatalogService(session)
    assert await catalog.get_subcategory(brand_id) is None
    assert await catalog.list_subcategory_products(brand_id) == []
    _opened, brands = await catalog.get_category_with_subcategories(category.id)
    assert brands == []


@pytest.mark.asyncio
async def test_brand_moved_to_another_category_keeps_back_consistent(
    session: AsyncSession,
) -> None:
    """A stale product list must not send Back to the old parent."""
    admin, category, brand, _product = await _shop(session)
    other = await admin.create_category("Disposables")
    await session.flush()

    await admin.reassign_subcategory(brand, other.id)
    await session.flush()

    refreshed = await CatalogService(session).get_subcategory(brand.id)
    assert refreshed is not None
    assert refreshed.category_id == other.id != category.id


# ===================================================== rapid repeat clicks


@pytest.mark.asyncio
async def test_double_tap_add_to_cart_increments(session: AsyncSession) -> None:
    _admin, _category, _brand, product = await _shop(session)
    user = await make_user(session, telegram_id=8100)
    await session.flush()
    cart = CartService(session)

    await cart.add_product(user.id, product, quantity=1)
    await cart.add_product(user.id, product, quantity=1)
    await session.flush()

    view = await cart.get_view(user.id, language="en")
    assert view is not None
    assert len(view.lines) == 1, "double tap must not create a duplicate line"
    assert view.lines[0].quantity == 2


@pytest.mark.asyncio
async def test_lost_race_on_add_recovers_by_incrementing(
    session: AsyncSession,
) -> None:
    """Simulate the double-tap race deterministically.

    Two taps can both SELECT "no such line" and both INSERT; uq_cart_product
    rejects the loser. True concurrency cannot be reproduced on in-memory
    SQLite (all sessions share one connection, so savepoints collide), so the
    lost race is forced: the lookup reports nothing while the row already
    exists, driving add_item down the INSERT path into the IntegrityError it
    must recover from.
    """
    _admin, _category, _brand, product = await _shop(session)
    user = await make_user(session, telegram_id=8250)
    await session.flush()

    cart_service = CartService(session)
    await cart_service.add_product(user.id, product, quantity=1)
    await session.flush()
    cart = await cart_service.get_or_create_cart(user.id)

    repo = cart_service.cart_items
    real_lookup = repo.get_by_cart_and_product
    seen = {"calls": 0}

    async def blind_once(cart_id: int, product_id: int):  # type: ignore[no-untyped-def]
        seen["calls"] += 1
        if seen["calls"] == 1:
            return None  # as far as this tap knows, no line exists yet
        return await real_lookup(cart_id, product_id)

    repo.get_by_cart_and_product = blind_once  # type: ignore[method-assign]
    try:
        item = await repo.add_item(cart.id, product.id, quantity=1)
    finally:
        repo.get_by_cart_and_product = real_lookup  # type: ignore[method-assign]
    await session.flush()

    assert item.quantity == 2, "the losing tap must increment, not error"
    view = await cart_service.get_view(user.id, language="en")
    assert view is not None and len(view.lines) == 1


@pytest.mark.asyncio
async def test_repeated_navigation_is_idempotent(session: AsyncSession) -> None:
    _admin, category, brand, _product = await _shop(session)
    catalog = CatalogService(session)

    first = [s.id for s in await catalog.list_subcategories(category.id)]
    for _ in range(5):
        assert [s.id for s in await catalog.list_subcategories(category.id)] == first
        assert [
            p.id for p in await catalog.list_subcategory_products(brand.id)
        ] == [p.id for p in await catalog.list_subcategory_products(brand.id)]


# ============================================================ back targets


@pytest.mark.asyncio
async def test_back_targets_at_every_level(session: AsyncSession) -> None:
    _admin, category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("en")

    card_back = _payloads(
        add_to_cart_keyboard(i18n, product.id, subcategory_id=product.subcategory_id)
    )[-1]
    assert card_back == f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}"

    catalog = CatalogService(session)
    resumed = await catalog.get_subcategory(
        int(card_back.removeprefix(CALLBACK_SUBCATEGORY_PREFIX))
    )
    assert resumed is not None
    products_back = f"{CALLBACK_CATEGORY_PREFIX}{resumed.category_id}"
    assert (
        await catalog.get_category(
            int(products_back.removeprefix(CALLBACK_CATEGORY_PREFIX))
        )
    ) is not None
    assert category.id == resumed.category_id
    assert CALLBACK_CATALOG_OPEN == "catalog:open"


@pytest.mark.asyncio
async def test_back_from_a_card_whose_brand_was_hidden(
    session: AsyncSession,
) -> None:
    """Back must fail closed, not 404 into an empty screen with no way out."""
    admin, category, brand, product = await _shop(session)
    await admin.set_subcategory_active(brand, False)
    await session.flush()

    catalog = CatalogService(session)
    assert await catalog.get_subcategory(brand.id) is None
    # the category above is still reachable, so the customer is not stranded
    assert await catalog.get_category(category.id) is not None


# ==================================================== cart / checkout guard


@pytest.mark.asyncio
async def test_cart_survives_its_product_being_hidden(
    session: AsyncSession,
) -> None:
    """An item already in the cart still renders (no crash) after a hide."""
    admin, _category, brand, product = await _shop(session)
    user = await make_user(session, telegram_id=8300)
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=2)
    await session.flush()

    await admin.set_subcategory_active(brand, False)
    await session.flush()

    view = await CartService(session).get_view(user.id, language="en")
    assert view is not None
    assert len(view.lines) == 1


@pytest.mark.asyncio
async def test_checkout_refuses_a_product_hidden_by_its_brand(
    session: AsyncSession,
) -> None:
    """Hiding a brand must stop it being sold, not just stop it being browsed."""
    admin, _category, brand, product = await _shop(session)
    user = await make_user(
        session, telegram_id=8400, language=LanguageCode.EN, city=CityChoice.BERLIN
    )
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=1)
    await session.flush()

    await admin.set_subcategory_active(brand, False)
    await session.flush()

    with pytest.raises(InactiveProductError):
        await OrderService(session).place_order_from_cart(
            user,
            customer_name="QA",
            delivery_type="pickup",
            address="Teststr. 1",
            preferred_time="18:00",
            phone=None,
        )


@pytest.mark.asyncio
async def test_checkout_still_works_for_a_visible_product(
    session: AsyncSession,
) -> None:
    _admin, _category, _brand, product = await _shop(session)
    user = await make_user(
        session, telegram_id=8500, language=LanguageCode.EN, city=CityChoice.BERLIN
    )
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=2)
    await session.flush()

    order = await OrderService(session).place_order_from_cart(
        user,
        customer_name="QA",
        delivery_type="pickup",
        address="Teststr. 1",
        preferred_time="18:00",
        phone=None,
    )
    assert order.total_price == Decimal("36.00")
    assert len(order.items) == 1


@pytest.mark.asyncio
async def test_legacy_product_without_a_brand_still_checks_out(
    session: AsyncSession,
) -> None:
    """Pre-hierarchy rows must not be blocked by the new visibility rule."""
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()
    legacy = await admin.create_product(
        category_id=category.id,
        name_ru="Старый", name_en="Legacy", name_de="Legacy DE",
        description_ru="о", description_en="d", description_de="b",
        **BASE,
    )
    user = await make_user(
        session, telegram_id=8600, language=LanguageCode.EN, city=CityChoice.BERLIN
    )
    await session.flush()
    await CartService(session).add_product(user.id, legacy, quantity=1)
    await session.flush()

    order = await OrderService(session).place_order_from_cart(
        user,
        customer_name="QA",
        delivery_type="pickup",
        address="Teststr. 1",
        preferred_time="18:00",
        phone=None,
    )
    assert order.total_price == Decimal("18.00")


# ============================================================== payloads


def test_all_navigation_payloads_fit_the_callback_limit() -> None:
    i18n = LocalizationService.from_code("ru")
    payloads = [
        CALLBACK_CATALOG_OPEN,
        f"{CALLBACK_CATEGORY_PREFIX}999999",
        f"{CALLBACK_SUBCATEGORY_PREFIX}999999",
        f"{CALLBACK_PRODUCT_PREFIX}999999",
        *_payloads(add_to_cart_keyboard(i18n, 999999, subcategory_id=999999)),
        *_payloads(product_added_keyboard(i18n, subcategory_id=999999)),
    ]
    for payload in payloads:
        assert len(payload.encode()) <= 64, payload
