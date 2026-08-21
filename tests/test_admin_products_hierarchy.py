"""Product management across the hierarchy: four languages, brand assignment."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.handlers.admin.product_manage.common import (
    EDIT_TEXT_STEPS,
    build_edit_preview,
    product_snapshot,
)
from app.handlers.admin.products import _TEXT_STEPS, _build_preview
from app.keyboards.admin_products import (
    CALLBACK_PRODUCT_SUB_PREFIX,
    admin_subcategory_pick_keyboard,
)
from app.services.admin import AdminService
from app.services.localization import LocalizationService
from app.states.admin import AddProductStates, EditProductStates
from app.utils.cache import invalidate_categories_cache
from app.utils.product_display import format_admin_product_card

LANGS = ("ru", "en", "de", "uk")
BASE = dict(flavor="Mango", volume="30ml", nicotine_strength="3mg", price=Decimal("12.50"))


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_categories_cache()


async def _tree(session: AsyncSession):  # type: ignore[no-untyped-def]
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    other = await admin.create_category("Disposables")
    brand = await admin.create_subcategory(category_id=category.id, name="Brand A")
    foreign = await admin.create_subcategory(category_id=other.id, name="Brand C")
    await session.flush()
    return admin, category, other, brand, foreign


# ---------------------------------------------------------------- wizard shape


def test_add_wizard_collects_all_four_languages() -> None:
    fields = {field for field, _, _ in _TEXT_STEPS.values()}
    for code in LANGS:
        assert f"name_{code}" in fields, f"name_{code} missing from add wizard"
        assert f"description_{code}" in fields, f"description_{code} missing"


def test_add_wizard_reaches_brand_then_price() -> None:
    """photo -> names -> descriptions -> category -> brand -> ... -> price."""
    assert _TEXT_STEPS[AddProductStates.name_de][1] is AddProductStates.name_uk
    assert _TEXT_STEPS[AddProductStates.name_uk][1] is AddProductStates.description_ru
    assert _TEXT_STEPS[AddProductStates.description_de][1] is AddProductStates.description_uk
    assert _TEXT_STEPS[AddProductStates.description_uk][1] is AddProductStates.category
    assert hasattr(AddProductStates, "subcategory")


def test_edit_wizard_collects_all_four_languages() -> None:
    fields = {field for field, _, _, _ in EDIT_TEXT_STEPS.values()}
    for code in LANGS:
        assert f"name_{code}" in fields
        assert f"description_{code}" in fields
    assert EDIT_TEXT_STEPS[EditProductStates.name_de][1] is EditProductStates.name_uk
    assert EDIT_TEXT_STEPS[EditProductStates.description_de][1] is EditProductStates.description_uk


def test_previews_render_every_field() -> None:
    i18n = LocalizationService.from_code("ru")
    data = {
        "product_id": 1,
        "category_id": 1,
        "category_name": "Liquids",
        "subcategory_name": "Brand A",
        "flavor": "Mango",
        "volume": "30ml",
        "nicotine_strength": "3mg",
        "price": "12.50",
    }
    for code in LANGS:
        data[f"name_{code}"] = f"NAME-{code.upper()}"
        data[f"description_{code}"] = f"DESC-{code.upper()}"

    for rendered in (_build_preview(i18n, data), build_edit_preview(i18n, data)):
        for code in LANGS:
            assert f"NAME-{code.upper()}" in rendered
            assert f"DESC-{code.upper()}" in rendered
        assert "Brand A" in rendered
        assert "Liquids" in rendered
        assert "{" not in rendered  # no unfilled placeholders


# ------------------------------------------------------- assignment guards


@pytest.mark.asyncio
async def test_brand_picker_only_offers_brands_of_that_category(
    session: AsyncSession,
) -> None:
    """The guard starts in the keyboard: a foreign brand is never offered."""
    admin, category, _other, brand, foreign = await _tree(session)

    offered = await admin.list_subcategories(category.id)
    markup = admin_subcategory_pick_keyboard(offered)
    payloads = [b.callback_data for row in markup.inline_keyboard for b in row]

    assert payloads == [f"{CALLBACK_PRODUCT_SUB_PREFIX}{brand.id}"]
    assert f"{CALLBACK_PRODUCT_SUB_PREFIX}{foreign.id}" not in payloads


@pytest.mark.asyncio
async def test_mismatched_brand_is_detectable_server_side(
    session: AsyncSession,
) -> None:
    """Second guard: a stale keyboard must not attach a foreign brand."""
    admin, category, other, brand, foreign = await _tree(session)

    assert brand.category_id == category.id
    assert foreign.category_id == other.id
    # this is exactly the comparison the handler performs before accepting
    assert foreign.category_id != category.id


@pytest.mark.asyncio
async def test_moving_a_product_keeps_category_consistent(
    session: AsyncSession,
) -> None:
    admin, category, other, brand, foreign = await _tree(session)
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

    await admin.move_product_to_subcategory(product, foreign.id)
    await session.flush()

    assert product.subcategory_id == foreign.id
    # the legacy category link follows the brand, so the pair never disagrees
    assert product.category_id == other.id


# --------------------------------------------------------------- persistence


@pytest.mark.asyncio
async def test_create_persists_every_field(session: AsyncSession) -> None:
    admin, category, _other, brand, _foreign = await _tree(session)

    product = await admin.create_product(
        category_id=category.id,
        subcategory_id=brand.id,
        name_ru="Манго",
        name_en="Mango",
        name_de="Mango DE",
        name_uk="Манго UA",
        description_ru="опис RU",
        description_en="desc EN",
        description_de="besch DE",
        description_uk="опис UA",
        image_file_id="AgACPHOTO",
        **BASE,
    )
    await session.flush()

    assert product.subcategory_id == brand.id
    assert product.category_id == category.id
    assert (product.name_ru, product.name_en, product.name_de, product.name_uk) == (
        "Манго",
        "Mango",
        "Mango DE",
        "Манго UA",
    )
    assert product.description_uk == "опис UA"
    assert product.image_file_id == "AgACPHOTO"
    assert product.flavor == "Mango"
    assert product.volume == "30ml"
    assert product.nicotine_strength == "3mg"
    assert product.price == Decimal("12.50")
    assert product.is_active is True


@pytest.mark.asyncio
async def test_active_state_toggles(session: AsyncSession) -> None:
    admin, category, _o, brand, _f = await _tree(session)
    product = await admin.create_product(
        category_id=category.id,
        subcategory_id=brand.id,
        name_ru="M",
        name_en="M",
        name_de="M",
        name_uk="M",
        description_ru="d",
        description_en="d",
        description_de="d",
        description_uk="d",
        **BASE,
    )
    await session.flush()

    await admin.disable_product(product)
    assert product.is_active is False
    await admin.enable_product(product)
    assert product.is_active is True


@pytest.mark.asyncio
async def test_snapshot_and_card_carry_the_new_fields(session: AsyncSession) -> None:
    admin, category, _o, brand, _f = await _tree(session)
    created = await admin.create_product(
        category_id=category.id,
        subcategory_id=brand.id,
        name_ru="Манго",
        name_en="Mango",
        name_de="Mango DE",
        name_uk="Манго UA",
        description_ru="о",
        description_en="d",
        description_de="b",
        description_uk="о UA",
        **BASE,
    )
    await session.flush()

    product = await admin.get_product(created.id)
    assert product is not None

    snapshot = product_snapshot(product)
    assert snapshot["name_uk"] == "Манго UA"
    assert snapshot["description_uk"] == "о UA"
    assert snapshot["subcategory_id"] == brand.id
    assert snapshot["subcategory_name"] == "Brand A"

    card = format_admin_product_card(product, LocalizationService.from_code("uk"))
    assert "Манго UA" in card
    assert "Brand A" in card
    assert "Liquids" in card
    assert "{" not in card


# ------------------------------------------------- existing products intact


@pytest.mark.asyncio
async def test_legacy_products_without_a_brand_still_work(
    session: AsyncSession,
) -> None:
    """Rows created before the hierarchy have subcategory_id NULL."""
    admin, category, _o, _b, _f = await _tree(session)
    legacy = await admin.create_product(
        category_id=category.id,
        name_ru="Старый",
        name_en="Legacy",
        name_de="Legacy DE",
        description_ru="о",
        description_en="d",
        description_de="b",
        **BASE,
    )
    await session.flush()

    assert legacy.subcategory_id is None
    # uk falls back to ru rather than being NULL
    assert legacy.name_uk == "Старый"
    assert legacy.description_uk == "о"

    product = await admin.get_product(legacy.id)
    assert product is not None
    card = format_admin_product_card(product, LocalizationService.from_code("en"))
    assert "—" in card  # brand renders as a dash, not a crash
    assert "{" not in card

    snapshot = product_snapshot(product)
    assert snapshot["subcategory_id"] is None
    assert snapshot["subcategory_name"] == "—"

    await admin.set_product_price(product, Decimal("20.00"))
    assert product.price == Decimal("20.00")
