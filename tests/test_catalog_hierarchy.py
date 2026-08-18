"""Catalog hierarchy: Category -> Subcategory -> Product."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Subcategory
from app.repositories.category import CategoryRepository
from app.repositories.product import ProductRepository
from app.repositories.subcategory import SubcategoryRepository

LANGS = ("ru", "en", "de", "uk")


@pytest.mark.asyncio
async def test_category_carries_four_localized_names(session: AsyncSession) -> None:
    category = await CategoryRepository(session).create_category("Liquids")
    await session.flush()

    for lang in LANGS:
        assert getattr(category, f"name_{lang}") == "Liquids"
    # Legacy column stays in sync so existing handlers keep rendering.
    assert category.name == "Liquids"
    assert category.is_active is True
    assert category.created_at is not None
    assert category.updated_at is not None


@pytest.mark.asyncio
async def test_rename_keeps_legacy_and_localized_in_sync(session: AsyncSession) -> None:
    repo = CategoryRepository(session)
    category = await repo.create_category("Liquids")
    await repo.rename(category, "E-Liquids")

    assert category.name == "E-Liquids"
    for lang in LANGS:
        assert getattr(category, f"name_{lang}") == "E-Liquids"


@pytest.mark.asyncio
async def test_subcategory_belongs_to_category(session: AsyncSession) -> None:
    category = await CategoryRepository(session).create_category("Liquids")
    repo = SubcategoryRepository(session)

    brand_a = await repo.create_subcategory(category_id=category.id, name="Brand A")
    brand_b = await repo.create_subcategory(category_id=category.id, name="Brand B")
    await session.flush()

    assert brand_a.category_id == category.id
    for lang in LANGS:
        assert getattr(brand_a, f"name_{lang}") == "Brand A"

    listed = await repo.list_by_category(category.id)
    assert [s.id for s in listed] == [brand_a.id, brand_b.id]
    assert brand_a.sort_order < brand_b.sort_order


@pytest.mark.asyncio
async def test_subcategory_active_state_filters(session: AsyncSession) -> None:
    category = await CategoryRepository(session).create_category("Liquids")
    repo = SubcategoryRepository(session)
    live = await repo.create_subcategory(category_id=category.id, name="Live")
    hidden = await repo.create_subcategory(category_id=category.id, name="Hidden")
    await repo.set_active(hidden, False)

    assert len(await repo.list_by_category(category.id)) == 2
    active = await repo.list_by_category(category.id, active_only=True)
    assert [s.id for s in active] == [live.id]


@pytest.mark.asyncio
async def test_product_belongs_to_subcategory(session: AsyncSession) -> None:
    category = await CategoryRepository(session).create_category("Liquids")
    sub = await SubcategoryRepository(session).create_subcategory(
        category_id=category.id, name="Brand A"
    )
    products = ProductRepository(session)

    product = await products.create_product(
        category_id=category.id,
        subcategory_id=sub.id,
        name_ru="Манго",
        name_en="Mango",
        name_de="Mango DE",
        name_uk="Манго UA",
        description_ru="опис",
        description_en="desc",
        description_de="besch",
        description_uk="опис UA",
        flavor="Mango",
        volume="30ml",
        nicotine_strength="3mg",
        price=Decimal("12.50"),
    )
    await session.flush()

    assert product.subcategory_id == sub.id
    assert product.name_uk == "Манго UA"
    assert product.description_uk == "опис UA"
    assert product.updated_at is not None

    listed = await products.list_by_subcategory(sub.id)
    assert [p.id for p in listed] == [product.id]
    assert await products.count_by_subcategory(sub.id) == 1


@pytest.mark.asyncio
async def test_ukrainian_falls_back_to_russian_when_not_supplied(
    session: AsyncSession,
) -> None:
    """Callers predating the four-language catalog must not write NULLs."""
    category = await CategoryRepository(session).create_category("Liquids")
    product = await ProductRepository(session).create_product(
        category_id=category.id,
        name_ru="Манго",
        name_en="Mango",
        name_de="Mango DE",
        description_ru="русский текст",
        description_en="desc",
        description_de="besch",
        flavor="Mango",
        volume="30ml",
        nicotine_strength="3mg",
        price=Decimal("9.90"),
    )
    await session.flush()

    assert product.name_uk == "Манго"
    assert product.description_uk == "русский текст"
    assert product.subcategory_id is None


@pytest.mark.asyncio
async def test_inactive_products_hidden_from_subcategory_listing(
    session: AsyncSession,
) -> None:
    category = await CategoryRepository(session).create_category("Liquids")
    sub = await SubcategoryRepository(session).create_subcategory(
        category_id=category.id, name="Brand A"
    )
    repo = ProductRepository(session)
    common = dict(
        category_id=category.id,
        subcategory_id=sub.id,
        name_en="P",
        name_de="P",
        description_ru="d",
        description_en="d",
        description_de="d",
        flavor="f",
        volume="30ml",
        nicotine_strength="3mg",
        price=Decimal("5.00"),
    )
    live = await repo.create_product(name_ru="Live", **common)
    await repo.create_product(name_ru="Hidden", is_active=False, **common)
    await session.flush()

    assert [p.id for p in await repo.list_by_subcategory(sub.id)] == [live.id]
    assert len(await repo.list_by_subcategory(sub.id, active_only=False)) == 2
    assert await repo.count_by_subcategory(sub.id) == 2


@pytest.mark.asyncio
async def test_full_hierarchy_traversal(session: AsyncSession) -> None:
    """Category -> Subcategory -> Product, the shape the catalog UI will walk."""
    categories = CategoryRepository(session)
    subs = SubcategoryRepository(session)
    products = ProductRepository(session)

    tree = {"Liquids": ("Brand A", "Brand B"), "Disposables": ("Brand C",)}
    for cat_name, brands in tree.items():
        category = await categories.create_category(cat_name)
        for brand in brands:
            sub = await subs.create_subcategory(category_id=category.id, name=brand)
            await products.create_product(
                category_id=category.id,
                subcategory_id=sub.id,
                name_ru=f"{brand} RU",
                name_en=brand,
                name_de=f"{brand} DE",
                description_ru="d",
                description_en="d",
                description_de="d",
                flavor="f",
                volume="30ml",
                nicotine_strength="3mg",
                price=Decimal("10.00"),
            )
    await session.flush()

    listed = await categories.list_ordered()
    assert [c.name_en for c in listed] == ["Liquids", "Disposables"]

    liquids = listed[0]
    brands = await subs.list_by_category(liquids.id)
    assert [s.name_en for s in brands] == ["Brand A", "Brand B"]
    assert len(await products.list_by_subcategory(brands[0].id)) == 1


@pytest.mark.asyncio
async def test_model_defaults_are_active(session: AsyncSession) -> None:
    category = Category(
        name="X", name_ru="X", name_en="X", name_de="X", name_uk="X"
    )
    session.add(category)
    await session.flush()
    sub = Subcategory(
        category_id=category.id, name_ru="Y", name_en="Y", name_de="Y", name_uk="Y"
    )
    session.add(sub)
    await session.flush()

    assert category.is_active is True
    assert sub.is_active is True
    assert sub.sort_order == 0
