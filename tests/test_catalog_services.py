"""Catalog service + repository layer: CRUD, visibility, ordering, safe deletion."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Subcategory
from app.repositories.category import CategoryRepository
from app.repositories.product import ProductRepository
from app.repositories.subcategory import SubcategoryRepository
from app.services.admin.catalog import AdminCatalogService
from app.services.admin.exceptions import (
    CategoryInUseError,
    ProductInUseError,
    SubcategoryInUseError,
)
from app.services.catalog import CatalogService
from app.utils.cache import invalidate_categories_cache

PRODUCT_DEFAULTS = dict(
    name_en="P",
    name_de="P",
    description_ru="d",
    description_en="d",
    description_de="d",
    flavor="f",
    volume="30ml",
    nicotine_strength="3mg",
    price=Decimal("10.00"),
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_categories_cache()


async def _tree(session: AsyncSession) -> tuple[Category, Subcategory, object]:
    """category -> subcategory -> product, all active."""
    category = await CategoryRepository(session).create_category("Liquids")
    sub = await SubcategoryRepository(session).create_subcategory(
        category_id=category.id, name="Brand A"
    )
    product = await ProductRepository(session).create_product(
        category_id=category.id,
        subcategory_id=sub.id,
        name_ru="Mango",
        **PRODUCT_DEFAULTS,
    )
    await session.flush()
    return category, sub, product


# ------------------------------------------------------------------ CRUD


@pytest.mark.asyncio
async def test_category_crud(session: AsyncSession) -> None:
    admin = AdminCatalogService(session)
    category = await admin.create_category("Liquids")
    assert category.is_active is True

    await admin.rename_category(category, "E-Liquids")
    assert category.name_uk == "E-Liquids"

    await admin.set_category_names(category, name_uk="Рідини", name_en="Liquids")
    assert category.name_uk == "Рідини"
    assert category.name_en == "Liquids"
    assert category.name_ru == "E-Liquids"

    await admin.delete_category(category)
    assert await admin.get_category(category.id) is None


@pytest.mark.asyncio
async def test_subcategory_crud(session: AsyncSession) -> None:
    admin = AdminCatalogService(session)
    category = await admin.create_category("Liquids")
    sub = await admin.create_subcategory(category_id=category.id, name="Brand A")
    await session.flush()

    assert sub.category_id == category.id
    assert sub.is_active is True

    await admin.rename_subcategory(sub, "Brand B")
    assert sub.name_de == "Brand B"

    await admin.set_subcategory_names(sub, name_uk="Бренд Б")
    assert sub.name_uk == "Бренд Б"
    assert sub.name_de == "Brand B"

    await admin.delete_subcategory(sub)
    assert await admin.get_subcategory(sub.id) is None


@pytest.mark.asyncio
async def test_set_names_rejects_unknown_field(session: AsyncSession) -> None:
    category = await CategoryRepository(session).create_category("Liquids")
    with pytest.raises(ValueError, match="Unknown localized name fields"):
        await CategoryRepository(session).set_names(category, name_pl="Płyny")


# ------------------------------------------------------ parent-child links


@pytest.mark.asyncio
async def test_reassigning_a_subcategory_moves_its_products(
    session: AsyncSession,
) -> None:
    admin = AdminCatalogService(session)
    _, sub, product = await _tree(session)
    other = await admin.create_category("Disposables")
    await session.flush()

    await admin.reassign_subcategory(sub, other.id)
    await admin.move_product_to_subcategory(product, sub.id)
    await session.flush()

    assert sub.category_id == other.id
    # the legacy direct link is kept in step, so nothing dangles
    assert product.category_id == other.id
    assert product.subcategory_id == sub.id


@pytest.mark.asyncio
async def test_moving_product_to_missing_subcategory_raises(
    session: AsyncSession,
) -> None:
    _, _, product = await _tree(session)
    with pytest.raises(ValueError, match="does not exist"):
        await ProductRepository(session).move_to_subcategory(product, 9999)


# ---------------------------------------------------------------- ordering


@pytest.mark.asyncio
async def test_subcategory_sort_order_and_move(session: AsyncSession) -> None:
    repo = SubcategoryRepository(session)
    category = await CategoryRepository(session).create_category("Liquids")
    a = await repo.create_subcategory(category_id=category.id, name="A")
    b = await repo.create_subcategory(category_id=category.id, name="B")
    c = await repo.create_subcategory(category_id=category.id, name="C")
    await session.flush()

    assert [s.name_en for s in await repo.list_by_category(category.id)] == ["A", "B", "C"]

    await repo.move(category.id, c.id, direction=-1)
    assert [s.name_en for s in await repo.list_by_category(category.id)] == ["A", "C", "B"]

    await repo.move(category.id, a.id, direction=-1)  # already first: no-op
    assert [s.name_en for s in await repo.list_by_category(category.id)] == ["A", "C", "B"]

    await repo.reorder(category.id, [b.id, a.id, c.id])
    assert [s.name_en for s in await repo.list_by_category(category.id)] == ["B", "A", "C"]


@pytest.mark.asyncio
async def test_reorder_ignores_subcategories_of_other_categories(
    session: AsyncSession,
) -> None:
    repo = SubcategoryRepository(session)
    cats = CategoryRepository(session)
    first = await cats.create_category("First")
    second = await cats.create_category("Second")
    mine = await repo.create_subcategory(category_id=first.id, name="Mine")
    theirs = await repo.create_subcategory(category_id=second.id, name="Theirs")
    await session.flush()

    reordered = await repo.reorder(first.id, [theirs.id, mine.id])

    assert [s.id for s in reordered] == [mine.id]
    assert theirs.sort_order != 0 or theirs.category_id == second.id


# -------------------------------------------------------------- visibility


@pytest.mark.asyncio
async def test_inactive_category_hidden_from_customers(session: AsyncSession) -> None:
    category, sub, product = await _tree(session)
    catalog = CatalogService(session)

    assert len(await catalog.list_categories()) == 1

    await AdminCatalogService(session).set_category_active(category, False)
    await session.flush()
    invalidate_categories_cache()

    assert await catalog.list_categories() == []
    assert await catalog.get_category(category.id) is None
    # cascade: the brand and product below it disappear too
    assert await catalog.list_subcategories(category.id) == []
    assert await catalog.get_subcategory(sub.id) is None
    assert await catalog.list_subcategory_products(sub.id) == []
    assert await catalog.get_product(product.id) is None


@pytest.mark.asyncio
async def test_inactive_subcategory_hides_its_products(session: AsyncSession) -> None:
    category, sub, product = await _tree(session)
    catalog = CatalogService(session)

    await AdminCatalogService(session).set_subcategory_active(sub, False)
    await session.flush()

    assert await catalog.list_subcategories(category.id) == []
    assert await catalog.get_subcategory(sub.id) is None
    assert await catalog.list_subcategory_products(sub.id) == []
    assert await catalog.get_product(product.id) is None
    # the category itself is still visible
    assert len(await catalog.list_categories()) == 1


@pytest.mark.asyncio
async def test_inactive_product_hidden_but_siblings_remain(
    session: AsyncSession,
) -> None:
    category, sub, product = await _tree(session)
    sibling = await ProductRepository(session).create_product(
        category_id=category.id,
        subcategory_id=sub.id,
        name_ru="Berry",
        **PRODUCT_DEFAULTS,
    )
    await session.flush()
    catalog = CatalogService(session)

    await AdminCatalogService(session).disable_product(product)
    await session.flush()

    visible = await catalog.list_subcategory_products(sub.id)
    assert [p.id for p in visible] == [sibling.id]
    assert await catalog.get_product(product.id) is None
    assert await catalog.get_product(sibling.id) is not None


@pytest.mark.asyncio
async def test_admin_still_sees_everything_inactive(session: AsyncSession) -> None:
    """Admin views must not inherit the customer visibility filter."""
    category, sub, product = await _tree(session)
    admin = AdminCatalogService(session)

    await admin.set_category_active(category, False)
    await admin.set_subcategory_active(sub, False)
    await admin.disable_product(product)
    await session.flush()
    invalidate_categories_cache()

    assert len(await admin.list_categories()) == 1
    assert len(await admin.list_subcategories(category.id)) == 1
    assert len(await admin.list_products()) == 1
    assert await admin.get_subcategory(sub.id) is not None
    # ...while the customer sees nothing
    assert await CatalogService(session).list_categories() == []


@pytest.mark.asyncio
async def test_admin_listing_is_not_served_from_the_customer_cache(
    session: AsyncSession,
) -> None:
    """Regression: both services once shared one cache holding active-only rows."""
    category, _, _ = await _tree(session)
    catalog = CatalogService(session)
    admin = AdminCatalogService(session)

    await catalog.list_categories()  # populates the customer cache
    await admin.set_category_active(category, False)
    await session.flush()

    assert len(await admin.list_categories()) == 1


@pytest.mark.asyncio
async def test_active_only_filters_on_repositories(session: AsyncSession) -> None:
    category, sub, _ = await _tree(session)
    cats, subs = CategoryRepository(session), SubcategoryRepository(session)
    await cats.set_active(category, False)
    await subs.set_active(sub, False)
    await session.flush()

    assert await cats.list_ordered(active_only=True) == []
    assert len(await cats.list_ordered()) == 1
    assert await subs.list_by_category(category.id, active_only=True) == []
    assert len(await subs.list_by_category(category.id)) == 1


# ---------------------------------------------------------- safe deletion


@pytest.mark.asyncio
async def test_category_with_subcategories_cannot_be_deleted(
    session: AsyncSession,
) -> None:
    category, _, _ = await _tree(session)
    with pytest.raises(CategoryInUseError, match="subcategory"):
        await AdminCatalogService(session).delete_category(category)


@pytest.mark.asyncio
async def test_subcategory_with_products_cannot_be_deleted(
    session: AsyncSession,
) -> None:
    _, sub, _ = await _tree(session)
    with pytest.raises(SubcategoryInUseError, match="product"):
        await AdminCatalogService(session).delete_subcategory(sub)


@pytest.mark.asyncio
async def test_safe_deletion_in_dependency_order(session: AsyncSession) -> None:
    """Emptying the tree from the leaves up is allowed at every step."""
    admin = AdminCatalogService(session)
    category, sub, product = await _tree(session)

    await admin.delete_product(product)
    await session.flush()
    await admin.delete_subcategory(sub)
    await session.flush()
    await admin.delete_category(category)
    await session.flush()

    assert await admin.list_categories() == []


@pytest.mark.asyncio
async def test_product_in_an_order_still_cannot_be_deleted(
    session: AsyncSession,
) -> None:
    from app.models.enums import OrderStatus
    from app.repositories.order import OrderRepository
    from tests.factories import make_user

    _, _, product = await _tree(session)
    user = await make_user(session, telegram_id=9100)
    await OrderRepository(session).create_order(
        user_id=user.id,
        customer_name="A",
        city="berlin",
        delivery_type="pickup",
        address="x",
        total_price=Decimal("10.00"),
        status=OrderStatus.NEW,
        items=[{"product_id": product.id, "quantity": 1, "price": "10.00"}],
    )
    await session.flush()

    with pytest.raises(ProductInUseError):
        await AdminCatalogService(session).delete_product(product)


# ------------------------------------------------------- efficient queries


@pytest.mark.asyncio
async def test_category_counts_use_a_single_query(session: AsyncSession) -> None:
    admin = AdminCatalogService(session)
    subs = SubcategoryRepository(session)
    products = ProductRepository(session)
    for name in ("Liquids", "Disposables", "Hardware"):
        category = await admin.create_category(name)
        for brand in ("A", "B"):
            sub = await subs.create_subcategory(category_id=category.id, name=brand)
            await products.create_product(
                category_id=category.id,
                subcategory_id=sub.id,
                name_ru=f"{name}{brand}",
                **PRODUCT_DEFAULTS,
            )
    await session.flush()

    statements: list[str] = []
    engine = session.get_bind()

    def _record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        rows = await admin.list_categories_with_counts()
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert [(c.name_en, s, p) for c, s, p in rows] == [
        ("Liquids", 2, 2),
        ("Disposables", 2, 2),
        ("Hardware", 2, 2),
    ]
    assert len(statements) == 1, f"expected 1 query, issued {len(statements)}"


@pytest.mark.asyncio
async def test_subcategory_counts_use_a_single_query(session: AsyncSession) -> None:
    admin = AdminCatalogService(session)
    category, sub, _ = await _tree(session)
    await SubcategoryRepository(session).create_subcategory(category_id=category.id, name="Empty")
    await session.flush()

    statements: list[str] = []
    engine = session.get_bind()

    def _record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        rows = await admin.list_subcategories_with_counts(category.id)
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert [(s.name_en, c) for s, c in rows] == [("Brand A", 1), ("Empty", 0)]
    assert len(statements) == 1, f"expected 1 query, issued {len(statements)}"


@pytest.mark.asyncio
async def test_tree_load_is_not_n_plus_one(session: AsyncSession) -> None:
    """selectinload keeps a full tree load at 2 queries regardless of size."""
    cats, subs = CategoryRepository(session), SubcategoryRepository(session)
    for name in ("A", "B", "C", "D"):
        category = await cats.create_category(name)
        for brand in ("x", "y", "z"):
            await subs.create_subcategory(category_id=category.id, name=f"{name}{brand}")
    await session.flush()
    session.expunge_all()

    statements: list[str] = []
    engine = session.get_bind()

    def _record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        tree = await cats.list_with_subcategories()
        loaded = [(c.name_en, len(c.subcategories)) for c in tree]
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert loaded == [("A", 3), ("B", 3), ("C", 3), ("D", 3)]
    assert len(statements) == 2, f"expected 2 queries, issued {len(statements)}"


@pytest.mark.asyncio
async def test_tree_load_filters_inactive_children(session: AsyncSession) -> None:
    cats, subs = CategoryRepository(session), SubcategoryRepository(session)
    category = await cats.create_category("Liquids")
    await subs.create_subcategory(category_id=category.id, name="Live")
    hidden = await subs.create_subcategory(category_id=category.id, name="Hidden")
    await subs.set_active(hidden, False)
    await session.flush()
    session.expunge_all()

    tree = await cats.list_with_subcategories(active_only=True)
    assert [s.name_en for s in tree[0].subcategories] == ["Live"]


@pytest.mark.asyncio
async def test_admin_product_listing_preloads_both_parents(
    session: AsyncSession,
) -> None:
    await _tree(session)
    await session.flush()
    session.expunge_all()

    products = await AdminCatalogService(session).list_products_with_parents()

    statements: list[str] = []
    engine = session.get_bind()

    def _record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        # touching the relationships must not emit further SQL
        rendered = [
            (p.category.name_en, p.subcategory.name_en if p.subcategory else None) for p in products
        ]
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert rendered == [("Liquids", "Brand A")]
    assert statements == []
