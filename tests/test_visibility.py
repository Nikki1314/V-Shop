"""
One definition of "on sale", exercised over every state a product can be in.

The checkout guard and the statistics rankings both answer this question. They
used to answer it with two separately written SQL conditions; this module pins
them to the shared predicate in :mod:`app.repositories.visibility` and to each
other, across the full matrix rather than the couple of cases each layer's own
tests happened to cover.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.repositories.product import ProductRepository
from app.repositories.statistics import StatisticsRepository
from app.repositories.visibility import only_sellable_products
from app.services.admin import AdminService

# (product active, brand state, category active) -> on sale?
#
# A product is on sale when it is active, its category is active, and — if it
# has a brand at all — that brand is active. "none" is a pre-hierarchy row.
MATRIX: tuple[tuple[bool, str, bool, bool], ...] = (
    (True, "none", True, True),
    (True, "none", False, False),
    (False, "none", True, False),
    (False, "none", False, False),
    (True, "active", True, True),
    (True, "active", False, False),
    (True, "inactive", True, False),
    (True, "inactive", False, False),
    (False, "active", True, False),
    (False, "active", False, False),
    (False, "inactive", True, False),
    (False, "inactive", False, False),
)


def label(product_active: bool, brand: str, category_active: bool) -> str:
    return (
        f"product={'active' if product_active else 'inactive'} "
        f"brand={brand} "
        f"category={'active' if category_active else 'inactive'}"
    )


@pytest.mark.asyncio
async def test_visibility_definition_is_shared(session: AsyncSession) -> None:
    """
    Every combination, checked three ways.

    The raw predicate, the checkout guard that must agree with it, and the
    statistics ranking that must agree with both.
    """
    admin = AdminService(session)
    expected: dict[int, bool] = {}
    described: dict[int, str] = {}

    for index, (product_active, brand, category_active, on_sale) in enumerate(MATRIX):
        category = await admin.create_category(f"cat{index}")
        await session.flush()
        subcategory_id = None
        if brand != "none":
            subcategory = await admin.create_subcategory(
                category_id=category.id, name=f"brand{index}"
            )
            await admin.set_subcategory_active(subcategory, brand == "active")
            await session.flush()
            subcategory_id = subcategory.id
        # set the category last: creating a subcategory under it must not flip it
        await admin.set_category_active(category, category_active)

        product = await admin.create_product(
            category_id=category.id,
            subcategory_id=subcategory_id,
            name_ru=f"p{index}",
            name_en=f"p{index}",
            name_de=f"p{index}",
            name_uk=f"p{index}",
            description_ru="d",
            description_en="d",
            description_de="d",
            description_uk="d",
            flavor="f",
            volume="30ml",
            nicotine_strength="3mg",
            price=Decimal("10.00"),
            is_active=product_active,
        )
        await session.flush()
        expected[product.id] = on_sale
        described[product.id] = label(product_active, brand, category_active)

    all_ids = list(expected)

    # 1. the predicate itself
    sellable = set((await session.scalars(only_sellable_products(select(Product.id)))).all())
    for product_id, on_sale in expected.items():
        assert (product_id in sellable) is on_sale, (
            f"predicate disagrees for {described[product_id]}"
        )

    # 2. the checkout guard, which must be its exact complement
    unsellable = await ProductRepository(session).list_unsellable_ids(all_ids)
    assert unsellable == set(all_ids) - sellable, (
        "the checkout guard and the shared predicate disagree"
    )

    # 3. the statistics ranking, over the same set
    ranked = {
        row.product_id
        for row in await StatisticsRepository(session).least_ordered_products(limit=len(MATRIX) * 2)
    }
    assert ranked == sellable, "the least-ordered list ranks a different set"


@pytest.mark.asyncio
async def test_an_unknown_id_counts_as_unsellable(session: AsyncSession) -> None:
    """A product deleted between add-to-cart and checkout must not be sold."""
    repository = ProductRepository(session)

    assert await repository.list_unsellable_ids([424_242]) == {424_242}
    assert await repository.list_unsellable_ids([]) == set()


@pytest.mark.asyncio
async def test_a_legacy_row_survives_the_brand_join(session: AsyncSession) -> None:
    """
    Regression: the brand join must be an OUTER join.

    An inner join would drop every pre-hierarchy product from the result, which
    reads as "not on sale" and would silently block checkout for them.
    """
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()
    legacy = await admin.create_product(
        category_id=category.id,
        name_ru="legacy",
        name_en="legacy",
        name_de="legacy",
        name_uk="legacy",
        description_ru="d",
        description_en="d",
        description_de="d",
        description_uk="d",
        flavor="f",
        volume="30ml",
        nicotine_strength="3mg",
        price=Decimal("10.00"),
    )
    await session.flush()

    assert legacy.subcategory_id is None
    sellable = set((await session.scalars(only_sellable_products(select(Product.id)))).all())
    assert legacy.id in sellable
    assert await ProductRepository(session).list_unsellable_ids([legacy.id]) == set()
