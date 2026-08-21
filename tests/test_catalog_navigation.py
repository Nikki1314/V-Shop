"""Customer catalog navigation: four levels, Back at every step, nothing hidden shown."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.cart import CALLBACK_CART_OPEN, CALLBACK_CONTINUE_SHOPPING
from app.keyboards.catalog import (
    CALLBACK_CATALOG_OPEN,
    CALLBACK_CATEGORY_PREFIX,
    CALLBACK_PRODUCT_PREFIX,
    CALLBACK_SUBCATEGORY_PREFIX,
    categories_keyboard,
    products_keyboard,
    subcategories_keyboard,
    subcategory_view_keyboard,
)
from app.keyboards.product import CALLBACK_CART_ADD_PREFIX, add_to_cart_keyboard
from app.services.admin import AdminService
from app.services.catalog import CatalogService
from app.services.localization import LocalizationService
from app.utils.cache import invalidate_categories_cache

BASE = dict(flavor="Mango", volume="30ml", nicotine_strength="3mg", price=Decimal("12.50"))


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_categories_cache()


def _payloads(markup) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _labels(markup) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.text for row in markup.inline_keyboard for b in row]


async def _shop(session: AsyncSession):  # type: ignore[no-untyped-def]
    """Liquids › Brand A › Mango, all active."""
    admin = AdminService(session)
    category = await admin.create_category(
        "Liquids",
        name_ru="Жидкости",
        name_en="Liquids",
        name_de="Liquids DE",
        name_uk="Рідини",
    )
    brand = await admin.create_subcategory(
        category_id=category.id,
        name="Brand A",
        name_ru="Бренд А",
        name_en="Brand A",
        name_de="Marke A",
        name_uk="Бренд А",
    )
    await session.flush()
    product = await admin.create_product(
        category_id=category.id,
        subcategory_id=brand.id,
        name_ru="Манго",
        name_en="Mango",
        name_de="Mango DE",
        name_uk="Манго UA",
        description_ru="о",
        description_en="d",
        description_de="b",
        description_uk="о",
        **BASE,
    )
    await session.flush()
    return admin, category, brand, product


# ------------------------------------------------------------ drill-down


@pytest.mark.asyncio
async def test_four_levels_resolve_in_order(session: AsyncSession) -> None:
    _admin, category, brand, product = await _shop(session)
    catalog = CatalogService(session)

    # 1. catalog -> categories
    categories = await catalog.list_categories()
    assert [c.id for c in categories] == [category.id]

    # 2. category -> brands
    opened, brands = await catalog.get_category_with_subcategories(category.id)
    assert opened is not None
    assert [s.id for s in brands] == [brand.id]

    # 3. brand -> products
    opened_brand, products = await catalog.get_subcategory_with_products(brand.id)
    assert opened_brand is not None
    assert [p.id for p in products] == [product.id]

    # 4. product -> card
    card = await catalog.get_product(product.id)
    assert card is not None and card.id == product.id


@pytest.mark.asyncio
async def test_each_level_links_to_the_next(session: AsyncSession) -> None:
    _admin, category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("en")
    catalog = CatalogService(session)

    cats = await catalog.list_categories()
    assert _payloads(categories_keyboard(cats, "en")) == [
        f"{CALLBACK_CATEGORY_PREFIX}{category.id}"
    ]

    brands = await catalog.list_subcategories(category.id)
    assert _payloads(subcategories_keyboard(i18n, brands))[0] == (
        f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}"
    )

    products = await catalog.list_subcategory_products(brand.id)
    assert _payloads(products_keyboard(i18n, products, category_id=category.id))[0] == (
        f"{CALLBACK_PRODUCT_PREFIX}{product.id}"
    )


# ------------------------------------------------------------------- back


@pytest.mark.asyncio
async def test_back_chain_walks_up_one_level_at_a_time(
    session: AsyncSession,
) -> None:
    """Card → products → brands → categories."""
    _admin, category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("en")
    catalog = CatalogService(session)

    # card -> products of its own brand
    card_kb = add_to_cart_keyboard(i18n, product.id, subcategory_id=product.subcategory_id)
    assert f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}" in _payloads(card_kb)

    # products -> brands of the parent category
    products = await catalog.list_subcategory_products(brand.id)
    assert _payloads(products_keyboard(i18n, products, category_id=category.id))[-1] == (
        f"{CALLBACK_CATEGORY_PREFIX}{category.id}"
    )

    # brands -> categories
    brands = await catalog.list_subcategories(category.id)
    assert _payloads(subcategories_keyboard(i18n, brands))[-1] == CALLBACK_CATALOG_OPEN


@pytest.mark.asyncio
async def test_back_context_is_derived_not_encoded(session: AsyncSession) -> None:
    """Parents come from the DB, so payloads stay tiny and cannot go stale."""
    _admin, category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("ru")

    kb = add_to_cart_keyboard(i18n, product.id, subcategory_id=product.subcategory_id)
    for payload in _payloads(kb):
        assert len(payload.encode()) <= 64, payload
    assert product.subcategory_id == brand.id
    assert brand.category_id == category.id


@pytest.mark.asyncio
async def test_empty_brand_still_offers_back(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    empty = await admin.create_subcategory(category_id=category.id, name="Empty")
    await session.flush()
    i18n = LocalizationService.from_code("en")

    assert await CatalogService(session).list_subcategory_products(empty.id) == []
    assert _payloads(subcategory_view_keyboard(i18n, category.id)) == [
        f"{CALLBACK_CATEGORY_PREFIX}{category.id}"
    ]


# ------------------------------------------------------------- visibility


@pytest.mark.asyncio
async def test_hidden_category_removes_the_whole_branch(
    session: AsyncSession,
) -> None:
    admin, category, brand, product = await _shop(session)
    await admin.set_category_active(category, False)
    await session.flush()
    invalidate_categories_cache()
    catalog = CatalogService(session)

    assert await catalog.list_categories() == []
    assert await catalog.list_subcategories(category.id) == []
    assert await catalog.list_subcategory_products(brand.id) == []
    assert await catalog.get_product(product.id) is None


@pytest.mark.asyncio
async def test_hidden_brand_removes_its_products(session: AsyncSession) -> None:
    admin, category, brand, product = await _shop(session)
    await admin.set_subcategory_active(brand, False)
    await session.flush()
    catalog = CatalogService(session)

    assert len(await catalog.list_categories()) == 1
    assert await catalog.list_subcategories(category.id) == []
    assert await catalog.get_subcategory(brand.id) is None
    assert await catalog.get_product(product.id) is None


@pytest.mark.asyncio
async def test_hidden_product_leaves_its_siblings(session: AsyncSession) -> None:
    admin, category, brand, product = await _shop(session)
    sibling = await admin.create_product(
        category_id=category.id,
        subcategory_id=brand.id,
        name_ru="Ягоды",
        name_en="Berry",
        name_de="Beere",
        name_uk="Ягоди",
        description_ru="о",
        description_en="d",
        description_de="b",
        description_uk="о",
        **BASE,
    )
    await session.flush()
    await admin.disable_product(product)
    await session.flush()

    catalog = CatalogService(session)
    visible = await catalog.list_subcategory_products(brand.id)
    assert [p.id for p in visible] == [sibling.id]
    assert await catalog.get_product(product.id) is None


# ------------------------------------------------------------------- cart


@pytest.mark.asyncio
async def test_product_card_keeps_the_cart_contract(session: AsyncSession) -> None:
    """The add-to-cart payload the cart handler listens for must not change."""
    _admin, _category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("en")

    payloads = _payloads(add_to_cart_keyboard(i18n, product.id, subcategory_id=brand.id))
    assert payloads[0] == f"{CALLBACK_CART_ADD_PREFIX}{product.id}"
    assert CALLBACK_CART_OPEN in payloads


def test_continue_shopping_returns_to_categories() -> None:
    """The cart's 'continue shopping' button reuses the catalog entry point."""
    assert CALLBACK_CONTINUE_SHOPPING == CALLBACK_CATALOG_OPEN


def test_card_without_context_omits_back_but_keeps_cart() -> None:
    i18n = LocalizationService.from_code("en")
    payloads = _payloads(add_to_cart_keyboard(i18n, 5))

    assert payloads[0] == f"{CALLBACK_CART_ADD_PREFIX}5"
    assert not any(p.startswith(CALLBACK_SUBCATEGORY_PREFIX) for p in payloads)


# -------------------------------------------------------------- labelling


@pytest.mark.asyncio
async def test_buttons_are_labelled_in_the_users_language(
    session: AsyncSession,
) -> None:
    _admin, category, brand, product = await _shop(session)
    catalog = CatalogService(session)
    cats = await catalog.list_categories()
    brands = await catalog.list_subcategories(category.id)
    products = await catalog.list_subcategory_products(brand.id)

    expected = {
        "ru": ("Жидкости", "Бренд А", "Манго"),
        "en": ("Liquids", "Brand A", "Mango"),
        "de": ("Liquids DE", "Marke A", "Mango DE"),
        "uk": ("Рідини", "Бренд А", "Манго UA"),
    }
    for code, (cat_name, brand_name, product_name) in expected.items():
        i18n = LocalizationService.from_code(code)
        assert _labels(categories_keyboard(cats, code))[0] == cat_name
        assert _labels(subcategories_keyboard(i18n, brands))[0] == brand_name
        assert (
            _labels(products_keyboard(i18n, products, category_id=category.id))[0] == product_name
        )


def test_no_callback_prefix_collides() -> None:
    """`catalog:open` must not be swallowed by the `category:` handler."""
    assert not CALLBACK_CATALOG_OPEN.startswith(CALLBACK_CATEGORY_PREFIX)
    for payload in (
        CALLBACK_CATALOG_OPEN,
        f"{CALLBACK_CATEGORY_PREFIX}1",
        f"{CALLBACK_SUBCATEGORY_PREFIX}1",
        f"{CALLBACK_PRODUCT_PREFIX}1",
        f"{CALLBACK_CART_ADD_PREFIX}1",
    ):
        matched = [
            p
            for p in (
                CALLBACK_CATEGORY_PREFIX,
                CALLBACK_SUBCATEGORY_PREFIX,
                CALLBACK_PRODUCT_PREFIX,
                "cart:",
            )
            if payload.startswith(p)
        ]
        assert len(matched) <= 1, f"{payload} matched {matched}"
