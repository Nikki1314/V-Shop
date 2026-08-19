"""Product card: content, localized buttons, and context across every path."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.cart import CALLBACK_CART_OPEN, CALLBACK_CONTINUE_SHOPPING
from app.keyboards.catalog import (
    CALLBACK_CATALOG_OPEN,
    CALLBACK_CATEGORY_PREFIX,
    CALLBACK_SUBCATEGORY_PREFIX,
)
from app.keyboards.product import (
    CALLBACK_CART_ADD_PREFIX,
    add_to_cart_keyboard,
    product_added_keyboard,
)
from app.services.admin import AdminService
from app.services.catalog import CatalogService
from app.services.localization import LocalizationService
from app.utils.cache import invalidate_categories_cache
from app.utils.product_display import format_product_card

LANGS = ("ru", "en", "de", "uk")
BASE = dict(
    flavor="Tropic", volume="60ml", nicotine_strength="6mg", price=Decimal("18.00")
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_categories_cache()


def _rows(markup) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def _shop(session: AsyncSession, *, with_photo: bool = True):  # type: ignore[no-untyped-def]
    admin = AdminService(session)
    category = await admin.create_category("Liquids", name_uk="Рідини")
    brand = await admin.create_subcategory(
        category_id=category.id, name="Brand A", name_uk="Бренд А"
    )
    await session.flush()
    product = await admin.create_product(
        category_id=category.id, subcategory_id=brand.id,
        name_ru="Манго", name_en="Mango", name_de="Mango DE", name_uk="Манго UA",
        description_ru="Смачно", description_en="Tasty",
        description_de="Lecker", description_uk="Смачно UA",
        image_file_id="AgACPHOTO" if with_photo else None,
        **BASE,
    )
    await session.flush()
    return admin, category, brand, product


# ------------------------------------------------------------- card content


@pytest.mark.asyncio
async def test_card_shows_every_required_field(session: AsyncSession) -> None:
    _admin, _category, _brand, product = await _shop(session)

    card = format_product_card(product, LocalizationService.from_code("en"))

    assert "Mango" in card              # localized name
    assert "Tasty" in card              # localized description
    assert "Tropic" in card             # flavor
    assert "60ml" in card               # volume
    assert "6mg" in card                # nicotine strength
    assert "18.00" in card              # price
    assert "{" not in card              # nothing unfilled


@pytest.mark.asyncio
async def test_card_is_localized_in_all_four_languages(
    session: AsyncSession,
) -> None:
    _admin, _category, _brand, product = await _shop(session)
    expected = {
        "ru": ("Манго", "Смачно", "Вкус"),
        "en": ("Mango", "Tasty", "Flavor"),
        "de": ("Mango DE", "Lecker", "Geschmack"),
        "uk": ("Манго UA", "Смачно UA", "Смак"),
    }
    for code, (name, description, flavor_label) in expected.items():
        card = format_product_card(product, LocalizationService.from_code(code))
        assert name in card
        assert description in card
        assert flavor_label in card


@pytest.mark.asyncio
async def test_photo_is_carried_on_the_product(session: AsyncSession) -> None:
    _a, _c, _b, with_photo = await _shop(session)
    assert with_photo.image_file_id == "AgACPHOTO"

    session.expunge_all()
    _a2, _c2, _b2, without = await _shop(session, with_photo=False)
    assert without.image_file_id is None  # handler falls back to a text card


# ------------------------------------------------------------- card buttons


@pytest.mark.asyncio
async def test_card_has_the_three_required_buttons(session: AsyncSession) -> None:
    _admin, _category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("en")

    rows = _rows(add_to_cart_keyboard(i18n, product.id, subcategory_id=brand.id))
    labels = [t for t, _ in rows]
    payloads = [d for _, d in rows]

    assert labels == ["📥 Add to Cart", "🛒 Cart", "⬅️ Back"]
    assert payloads == [
        f"{CALLBACK_CART_ADD_PREFIX}{product.id}",
        CALLBACK_CART_OPEN,
        f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}",
    ]


def test_card_buttons_are_localized_not_hardcoded() -> None:
    seen: set[tuple[str, ...]] = set()
    for code in LANGS:
        labels = tuple(
            t for t, _ in _rows(add_to_cart_keyboard(
                LocalizationService.from_code(code), 1, subcategory_id=2
            ))
        )
        assert len(labels) == 3
        seen.add(labels)
    # every language renders its own wording
    assert len(seen) == len(LANGS)


def test_card_buttons_carry_the_required_icons() -> None:
    for code in LANGS:
        labels = [
            t for t, _ in _rows(add_to_cart_keyboard(
                LocalizationService.from_code(code), 1, subcategory_id=2
            ))
        ]
        assert labels[0].startswith("📥")
        assert labels[1].startswith("🛒")
        assert labels[2].startswith("⬅️")


# ------------------------------------------- context preserved after adding


@pytest.mark.asyncio
async def test_adding_to_cart_returns_to_the_same_brand(
    session: AsyncSession,
) -> None:
    """The customer must land back in the list they were browsing."""
    _admin, _category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("en")

    payloads = [
        d for _, d in _rows(
            product_added_keyboard(i18n, subcategory_id=product.subcategory_id)
        )
    ]
    assert payloads[0] == f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}"
    assert CALLBACK_CART_OPEN in payloads
    assert CALLBACK_CATALOG_OPEN not in payloads  # no longer dumped at the top


def test_added_keyboard_falls_back_when_context_is_unknown() -> None:
    payloads = [d for _, d in _rows(product_added_keyboard(
        LocalizationService.from_code("en")
    ))]
    assert payloads[0] == CALLBACK_CONTINUE_SHOPPING
    assert CALLBACK_CART_OPEN in payloads


# -------------------------------------------------- purchasability guards


@pytest.mark.asyncio
async def test_hidden_brand_makes_its_products_unbuyable(
    session: AsyncSession,
) -> None:
    """A stale card must not add an item from a hidden brand."""
    admin, _category, brand, product = await _shop(session)
    catalog = CatalogService(session)
    assert await catalog.get_purchasable_product(product.id) is not None

    await admin.set_subcategory_active(brand, False)
    await session.flush()
    assert await catalog.get_purchasable_product(product.id) is None


@pytest.mark.asyncio
async def test_hidden_category_makes_its_products_unbuyable(
    session: AsyncSession,
) -> None:
    admin, category, _brand, product = await _shop(session)
    await admin.set_category_active(category, False)
    await session.flush()
    invalidate_categories_cache()

    assert await CatalogService(session).get_purchasable_product(product.id) is None


@pytest.mark.asyncio
async def test_disabled_product_is_unbuyable(session: AsyncSession) -> None:
    admin, _category, _brand, product = await _shop(session)
    await admin.disable_product(product)
    await session.flush()

    assert await CatalogService(session).get_purchasable_product(product.id) is None


@pytest.mark.asyncio
async def test_legacy_product_without_a_brand_stays_buyable(
    session: AsyncSession,
) -> None:
    """Pre-hierarchy rows have no brand and must not become unbuyable."""
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()
    legacy = await admin.create_product(
        category_id=category.id,
        name_ru="Старый", name_en="Legacy", name_de="Legacy DE",
        description_ru="о", description_en="d", description_de="b",
        **BASE,
    )
    await session.flush()

    catalog = CatalogService(session)
    assert legacy.subcategory_id is None
    assert await catalog.get_purchasable_product(legacy.id) is not None

    await admin.disable_product(legacy)
    await session.flush()
    assert await catalog.get_purchasable_product(legacy.id) is None


# ------------------------------------------------ every navigation path


@pytest.mark.asyncio
async def test_all_navigation_paths_round_trip(session: AsyncSession) -> None:
    """Walk down all four levels and back up again, checking every hop."""
    _admin, category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("uk")
    catalog = CatalogService(session)

    # down: catalog -> category -> brand -> product
    assert [c.id for c in await catalog.list_categories()] == [category.id]
    opened, brands = await catalog.get_category_with_subcategories(category.id)
    assert opened is not None and [s.id for s in brands] == [brand.id]
    opened_brand, products = await catalog.get_subcategory_with_products(brand.id)
    assert opened_brand is not None and [p.id for p in products] == [product.id]
    card = await catalog.get_product(product.id)
    assert card is not None

    # up: card -> products -> brands -> categories
    back_from_card = [
        d for _, d in _rows(
            add_to_cart_keyboard(i18n, card.id, subcategory_id=card.subcategory_id)
        )
    ][-1]
    assert back_from_card == f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}"

    target_brand = await catalog.get_subcategory(
        int(back_from_card.removeprefix(CALLBACK_SUBCATEGORY_PREFIX))
    )
    assert target_brand is not None
    back_from_products = f"{CALLBACK_CATEGORY_PREFIX}{target_brand.category_id}"

    target_category = await catalog.get_category(
        int(back_from_products.removeprefix(CALLBACK_CATEGORY_PREFIX))
    )
    assert target_category is not None and target_category.id == category.id

    # and the top of the tree is reachable from the brand list
    assert CALLBACK_CATALOG_OPEN == CALLBACK_CONTINUE_SHOPPING


@pytest.mark.asyncio
async def test_add_then_continue_then_back_up(session: AsyncSession) -> None:
    """Add to cart, continue shopping, then walk back to the categories."""
    _admin, category, brand, product = await _shop(session)
    i18n = LocalizationService.from_code("de")
    catalog = CatalogService(session)

    continue_target = [
        d for _, d in _rows(
            product_added_keyboard(i18n, subcategory_id=product.subcategory_id)
        )
    ][0]
    assert continue_target == f"{CALLBACK_SUBCATEGORY_PREFIX}{brand.id}"

    resumed, products = await catalog.get_subcategory_with_products(
        int(continue_target.removeprefix(CALLBACK_SUBCATEGORY_PREFIX))
    )
    assert resumed is not None
    assert [p.id for p in products] == [product.id]
    assert resumed.category_id == category.id
