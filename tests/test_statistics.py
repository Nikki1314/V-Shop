"""
Statistics service, verified against one fully enumerated dataset.

Determinism rules for this module:

* The clock is frozen at :data:`NOW`. Nothing here reads the wall clock — every
  ``collect()`` call is handed an explicit moment, and
  ``test_the_suite_never_reads_the_wall_clock`` fails the module if that slips.
* The dataset is declared as data in :data:`PRODUCTS` and :data:`ORDERS`, not
  built ad hoc per test, so every expected number below can be recomputed by
  reading those two tables rather than by running the code.
* Products are created in the order listed, so ties in the popularity lists
  break on id in that same order. The expected orderings assert the tie-break.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus, PaymentMethod
from app.models.order import Order, OrderItem
from app.repositories.statistics import StatisticsRepository
from app.services.admin import AdminService
from app.services.statistics import ShopStatistics, StatisticsService
from app.utils.periods import DEFAULT_TIMEZONE, month_bounds, resolve_timezone
from tests import shop_dataset
from tests.shop_dataset import (
    AUGUST_START,
    BERLIN,
    HIDDEN_BRAND,
    JULY_START,
    NOW,
    ON_SALE,
    ORDERS,
    PRODUCTS,
    RETIRED_CATEGORY,
    SEPTEMBER_START,
    Shop,
    at,
    names,
)

# ========================================================== the dataset itself


def test_the_dataset_covers_every_required_case() -> None:
    """Guards the fixture: a later edit must not quietly drop a case."""
    statuses = {status for _, _, status, _, _ in ORDERS}
    assert statuses == {
        OrderStatus.NEW,
        OrderStatus.ACCEPTED,
        OrderStatus.SHIPPED,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
    }, "every order status must appear in the dataset"

    months = {when.month for _, when, _, _, _ in ORDERS}
    assert {3, 6, 7, 8} <= months, "older, previous-month and current-month orders"

    assert max(len(lines) for *_, lines in ORDERS) > 1, "an order with two lines"
    assert max(q for *_, lines in ORDERS for _, q in lines) > 1, "a line with many units"

    repeated = [
        label for label, _, _, _, lines in ORDERS
        if len({key for key, _ in lines}) < len(lines)
    ]
    assert repeated == ["jul-two-lines"], "one order repeats a product across lines"

    ordered = {key for *_, lines in ORDERS for key, _ in lines}
    assert {key for key, *_ in PRODUCTS} - ordered == {"void", "ghost"}, (
        "products that were never ordered"
    )

    placements = {placement for *_, placement in PRODUCTS}
    assert placements == {ON_SALE, HIDDEN_BRAND, RETIRED_CATEGORY}, (
        "every way of being off sale must be represented"
    )
    assert not all(active for _, active, _ in PRODUCTS), "an inactive product"


def test_the_suite_never_reads_the_wall_clock() -> None:
    """
    No test here may depend on today's date.

    Enforced on the source of this module and of the dataset it seeds from,
    rather than by convention: a single ``collect()`` with no argument would
    silently make the whole suite time-dependent — green today, red on the
    first of the month.
    """
    sources = [pathlib.Path(__file__), pathlib.Path(shop_dataset.__file__)]
    banned = {"now", "today", "utcnow", "fromtimestamp"}
    offenders: list[str] = []
    collects: list[str] = []

    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            ):
                continue
            where = f"{path.name}:{node.lineno}"
            if node.func.attr in banned:
                offenders.append(f"{where} {ast.unparse(node)}")
            elif node.func.attr == "collect":
                collects.append(where)
                if not (node.args or node.keywords):
                    offenders.append(
                        f"{where} collect() without an explicit moment falls back "
                        "to datetime.now()"
                    )

    assert collects, "sanity: the suite should call collect()"
    assert offenders == [], f"wall-clock read in a deterministic test: {offenders}"


# =================================================================== general


@pytest.mark.asyncio
async def test_general_counts_are_exact(stats: ShopStatistics) -> None:
    assert stats.general.users == 3
    assert stats.general.categories == 2
    assert stats.general.active_categories == 1
    assert stats.general.subcategories == 3
    assert stats.general.active_subcategories == 2
    assert stats.general.products == 8
    assert stats.general.active_products == 7
    assert stats.general.orders == 18
    assert stats.general.carts == 0


# ==================================================== month boundaries / zone


def test_month_bounds_are_half_open() -> None:
    bounds = month_bounds(NOW, "Europe/Berlin")

    assert bounds.current == (AUGUST_START, SEPTEMBER_START)
    assert bounds.previous == (JULY_START, AUGUST_START)


def test_month_bounds_roll_over_year_ends() -> None:
    january = month_bounds(datetime(2026, 1, 15, tzinfo=BERLIN), "Europe/Berlin")
    assert january.previous_start == datetime(2025, 12, 1, tzinfo=BERLIN)

    december = month_bounds(datetime(2026, 12, 15, tzinfo=BERLIN), "Europe/Berlin")
    assert december.next_start == datetime(2027, 1, 1, tzinfo=BERLIN)


def test_dst_does_not_shift_a_month_start() -> None:
    """Berlin is +01:00 in winter and +02:00 in summer; both start at midnight."""
    winter = month_bounds(datetime(2026, 1, 15, tzinfo=BERLIN), "Europe/Berlin")
    summer = month_bounds(datetime(2026, 7, 15, tzinfo=BERLIN), "Europe/Berlin")

    assert (winter.current_start.hour, summer.current_start.hour) == (0, 0)
    assert winter.current_start.utcoffset() == timedelta(hours=1)
    assert summer.current_start.utcoffset() == timedelta(hours=2)


def test_the_same_instant_starts_a_different_month_per_zone() -> None:
    instant = datetime(2026, 8, 31, 23, 30, tzinfo=UTC)  # already 1 Sep in Berlin

    assert month_bounds(instant, "Europe/Berlin").current_start == SEPTEMBER_START
    assert month_bounds(instant, "UTC").current_start == datetime(
        2026, 8, 1, tzinfo=ZoneInfo("UTC")
    )


def test_timezone_falls_back_instead_of_crashing() -> None:
    assert resolve_timezone("Europe/Berlin").key == "Europe/Berlin"
    assert resolve_timezone("Not/AZone").key == DEFAULT_TIMEZONE
    assert resolve_timezone(None).key == DEFAULT_TIMEZONE


@pytest.mark.asyncio
async def test_default_timezone_is_berlin(stats: ShopStatistics) -> None:
    assert stats.timezone == "Europe/Berlin"
    assert stats.bounds.current_start == AUGUST_START


def test_config_default_matches_the_period_helper() -> None:
    """A caller that omits the zone must land on the configured default."""
    from app.config import Settings

    assert Settings.model_fields["app_timezone"].default == DEFAULT_TIMEZONE


@pytest.mark.asyncio
async def test_orders_split_exactly_at_local_midnight(stats: ShopStatistics) -> None:
    """
    ``jul-last-minute`` at 23:59 and ``aug-first-instant`` at 00:00 straddle it.

    The range is half-open, so the order created exactly at midnight belongs to
    the month starting then and to no other. ``jul-first-instant`` proves the
    same for the opening edge of the previous month.
    """
    assert stats.previous_month.orders.total == 6
    assert stats.current_month.orders.total == 9
    # 1.00 is jul-last-minute, 2.00 is jul-first-instant, 10.00 is aug-first-instant
    assert stats.previous_month.revenue == Decimal("83.00")
    assert stats.current_month.revenue == Decimal("82.00")


@pytest.mark.asyncio
async def test_a_different_zone_moves_the_boundary(
    session: AsyncSession, shop: Shop
) -> None:
    september = datetime(2026, 9, 15, 12, 0, tzinfo=BERLIN)

    berlin = await StatisticsService(session, "Europe/Berlin").collect(september)
    honolulu = await StatisticsService(session, "Pacific/Honolulu").collect(september)

    assert berlin.timezone == "Europe/Berlin"
    assert honolulu.timezone == "Pacific/Honolulu"
    assert berlin.bounds.current_start.astimezone(UTC) == datetime(
        2026, 8, 31, 22, 0, tzinfo=UTC
    )
    assert honolulu.bounds.current_start.astimezone(UTC) == datetime(
        2026, 9, 1, 10, 0, tzinfo=UTC
    )


class _RecordingStats(StatisticsRepository):
    """Delegates to the real repository, remembering the periods it was asked for."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.windows: list[tuple[datetime | None, datetime | None]] = []

    async def order_counts(self, *, since=None, until=None):  # type: ignore[no-untyped-def]
        self.windows.append((since, until))
        return await super().order_counts(since=since, until=until)

    async def completed_revenue(self, *, since=None, until=None):  # type: ignore[no-untyped-def]
        self.windows.append((since, until))
        return await super().completed_revenue(since=since, until=until)


@pytest.mark.asyncio
async def test_period_filters_are_local_midnight_as_real_instants(
    session: AsyncSession,
) -> None:
    """
    Asserted on the values the repository receives, not on rows.

    SQLite drops ``tzinfo`` and compares wall clocks, so an end-to-end cross-zone
    assertion here would be measuring the fixture. These same values bind to
    ``timestamptz`` on PostgreSQL and compare as instants. September in Berlin
    begins at 22:00 UTC on 31 August.
    """
    service = StatisticsService(session, "Europe/Berlin")
    recorder = _RecordingStats(session)
    service.stats = recorder

    await service.collect(datetime(2026, 9, 15, 12, 0, tzinfo=BERLIN))

    assert (None, None) in recorder.windows, "all-time must be unbounded"
    bounded = [window for window in recorder.windows if window != (None, None)]
    assert bounded, "no bounded period was queried"
    for since, until in bounded:
        assert since is not None and since.tzinfo is not None
        assert until is not None and until.tzinfo is not None

    as_utc = {(s.astimezone(UTC), u.astimezone(UTC)) for s, u in bounded}
    assert (
        datetime(2026, 8, 31, 22, 0, tzinfo=UTC),
        datetime(2026, 9, 30, 22, 0, tzinfo=UTC),
    ) in as_utc, "current month is September in Berlin"
    assert (
        datetime(2026, 7, 31, 22, 0, tzinfo=UTC),
        datetime(2026, 8, 31, 22, 0, tzinfo=UTC),
    ) in as_utc, "previous month is August in Berlin"


# ==================================================================== orders


@pytest.mark.asyncio
async def test_all_time_order_counts_are_exact(stats: ShopStatistics) -> None:
    counts = stats.all_time.orders

    assert counts.total == 18
    assert counts.completed == 11
    assert counts.cancelled == 3
    assert counts.other == 4  # two New, one Accepted, one Shipped


@pytest.mark.asyncio
async def test_current_month_order_counts_are_exact(stats: ShopStatistics) -> None:
    counts = stats.current_month.orders

    assert counts.total == 9
    assert counts.completed == 5
    assert counts.cancelled == 1
    assert counts.other == 3  # Accepted, Shipped, New


@pytest.mark.asyncio
async def test_previous_month_order_counts_are_exact(stats: ShopStatistics) -> None:
    counts = stats.previous_month.orders

    assert counts.total == 6
    assert counts.completed == 4
    assert counts.cancelled == 1
    assert counts.other == 1  # one New


@pytest.mark.asyncio
async def test_older_orders_reach_all_time_only(stats: ShopStatistics) -> None:
    """The March and June orders must not leak into either month."""
    monthly = stats.current_month.orders.total + stats.previous_month.orders.total
    assert stats.all_time.orders.total - monthly == 3

    monthly_revenue = stats.current_month.revenue + stats.previous_month.revenue
    # mar-completed 25.00 + jun-last-minute 3.00; mar-cancelled contributes nothing
    assert stats.all_time.revenue - monthly_revenue == Decimal("28.00")


# =================================================================== revenue


@pytest.mark.asyncio
async def test_revenue_is_completed_only_in_every_period(
    stats: ShopStatistics,
) -> None:
    assert stats.all_time.revenue == Decimal("193.00")
    assert stats.current_month.revenue == Decimal("82.00")
    assert stats.previous_month.revenue == Decimal("83.00")


@pytest.mark.asyncio
async def test_revenue_ignores_every_non_completed_status(
    stats: ShopStatistics,
) -> None:
    """
    August holds 82.00 of completed orders against 310.00 of everything else.

    Accepted (70), Shipped (80), New (60) and Cancelled (100) all contribute
    nothing — a bug that counted any one of them would show up here.
    """
    ignored = sum(
        Decimal(total)
        for _, when, status, total, _ in ORDERS
        if status is not OrderStatus.COMPLETED and when >= AUGUST_START
    )

    assert ignored == Decimal("310.00")
    assert stats.current_month.revenue == Decimal("82.00")


@pytest.mark.asyncio
async def test_revenue_uses_the_stored_order_total(
    session: AsyncSession, shop: Shop
) -> None:
    """Repricing a product must not move historical revenue."""
    before = (await StatisticsService(session).collect(NOW)).all_time.revenue
    await AdminService(session).set_product_price(
        shop.products["mango"], Decimal("999.00")
    )
    await session.flush()

    after = (await StatisticsService(session).collect(NOW)).all_time.revenue

    assert before == after == Decimal("193.00")


# ================================================================ popularity


@pytest.mark.asyncio
async def test_top_three_most_ordered_are_exact(stats: ShopStatistics) -> None:
    assert names(stats.most_ordered) == [("mango", 5), ("berry", 4), ("ice", 1)]


@pytest.mark.asyncio
async def test_bottom_three_least_ordered_are_exact(stats: ShopStatistics) -> None:
    """
    ``mint`` and ``void`` both sit at zero; the tie breaks on id, which is
    creation order. ``ghost`` is inactive and never appears.
    """
    assert names(stats.least_ordered) == [("mint", 0), ("void", 0), ("ice", 1)]


@pytest.mark.asyncio
async def test_popularity_counts_distinct_orders_not_units(
    session: AsyncSession, shop: Shop
) -> None:
    """
    ``berry`` sells 5 units inside ``jul-two-lines`` alone, across two lines.

    That order contributes exactly 1 to berry's count. ``mango`` sells 2 units on
    a single line of ``aug-multi-qty`` and likewise contributes 1.
    """
    berry_units = sum(q for *_, lines in ORDERS for key, q in lines if key == "berry")
    assert berry_units == 9, "the dataset really does sell berry many times over"

    counts = dict(
        names(await StatisticsRepository(session).most_ordered_products(limit=6))
    )

    assert counts["berry"] == 4, "4 distinct completed orders, not 9 units"
    assert counts["mango"] == 5, "5 distinct completed orders, not 6 completed units"


@pytest.mark.asyncio
async def test_only_completed_orders_feed_popularity(
    session: AsyncSession, shop: Shop
) -> None:
    """``mint`` appears in a cancelled and a new order, and must count zero."""
    mint_orders = [
        label for label, _, _, _, lines in ORDERS
        if any(key == "mint" for key, _ in lines)
    ]
    assert mint_orders == ["jul-cancelled", "aug-new", "aug-cancelled"]

    repository = StatisticsRepository(session)
    most = dict(names(await repository.most_ordered_products(limit=6)))
    least = dict(names(await repository.least_ordered_products(limit=6)))

    assert "mint" not in most, "a product with no completed order is not 'most ordered'"
    assert least["mint"] == 0


@pytest.mark.asyncio
async def test_zero_order_products_qualify_for_the_bottom_list(
    session: AsyncSession, shop: Shop
) -> None:
    """``void`` has never been in any order at all — that is the point of the list."""
    least = await StatisticsRepository(session).least_ordered_products(limit=6)

    assert names(least) == [
        ("mint", 0), ("void", 0), ("ice", 1), ("berry", 4), ("mango", 5)
    ]
    assert "ghost" not in {row.name_en for row in least}, "inactive products excluded"


@pytest.mark.asyncio
async def test_both_lists_are_capped_at_three(stats: ShopStatistics) -> None:
    assert len(stats.most_ordered) == 3
    assert len(stats.least_ordered) == 3


@pytest.mark.asyncio
async def test_the_two_lists_are_opposite_ends_of_one_ranking(
    session: AsyncSession, shop: Shop
) -> None:
    repository = StatisticsRepository(session)
    full = names(await repository.least_ordered_products(limit=99))
    least = names(await repository.least_ordered_products(limit=3))
    most = names(await repository.most_ordered_products(limit=3))

    assert least == full[:3]
    assert [name for name, _ in most] == [name for name, _ in reversed(full)][:3]


@pytest.mark.asyncio
async def test_neither_list_shows_a_product_that_is_off_sale(
    session: AsyncSession, shop: Shop
) -> None:
    """
    Both rankings cover products on sale, and only those.

    ``shelved`` and ``archived`` each have a completed order, so they would rank
    on order count alone. They are excluded because their brand and their
    category respectively are deactivated — the same rule that keeps them out of
    the customer catalog and out of a checkout.
    """
    repository = StatisticsRepository(session)
    most = {name for name, _ in names(await repository.most_ordered_products(limit=99))}
    least = {name for name, _ in names(await repository.least_ordered_products(limit=99))}

    for hidden, reason in (
        ("ghost", "the product itself is inactive"),
        ("shelved", "its brand is deactivated"),
        ("archived", "its category is deactivated"),
    ):
        assert hidden not in most, f"{hidden} ranked as a bestseller: {reason}"
        assert hidden not in least, f"{hidden} ranked as a worst seller: {reason}"

    assert most == {"mango", "berry", "ice"}
    assert least == {"mango", "berry", "ice", "mint", "void"}


@pytest.mark.asyncio
async def test_hiding_a_parent_removes_a_product_from_the_lists(
    session: AsyncSession, shop: Shop
) -> None:
    """The rule is dynamic: deactivating a brand takes its product off the list."""
    admin = AdminService(session)
    repository = StatisticsRepository(session)

    before = {name for name, _ in names(await repository.most_ordered_products(limit=99))}
    assert "mango" in before

    await admin.set_subcategory_active(shop.active_subcategory, False)
    await session.flush()
    without_brand = names(await repository.most_ordered_products(limit=99))
    assert without_brand == [], "every ranked product sat under that one brand"

    await admin.set_subcategory_active(shop.active_subcategory, True)
    await admin.set_category_active(shop.active_category, False)
    await session.flush()
    without_category = names(await repository.least_ordered_products(limit=99))
    assert without_category == [], "the category is hidden, so nothing is on sale"

    await admin.set_category_active(shop.active_category, True)
    await session.flush()
    assert {
        name for name, _ in names(await repository.most_ordered_products(limit=99))
    } == before, "restoring both parents restores the ranking"


@pytest.mark.asyncio
async def test_a_product_with_no_brand_is_judged_on_its_category(
    session: AsyncSession, shop: Shop
) -> None:
    """
    Pre-hierarchy rows carry no subcategory and must not be judged on one.

    They are still subject to their category: ``products.category_id`` is NOT
    NULL on every row, so a legacy product under a retired category is off sale
    just like a hierarchy one.
    """
    admin = AdminService(session)
    common = dict(
        description_ru="d", description_en="d", description_de="d", description_uk="d",
        flavor="f", volume="30ml", nicotine_strength="3mg", price=Decimal("10.00"),
    )
    legacy = await admin.create_product(
        category_id=shop.active_category.id,
        name_ru="legacy", name_en="legacy", name_de="legacy", name_uk="legacy",
        **common,
    )
    stranded = await admin.create_product(
        category_id=shop.disabled_category.id,
        name_ru="stranded", name_en="stranded", name_de="stranded", name_uk="stranded",
        **common,
    )
    await session.flush()
    assert legacy.subcategory_id is None and stranded.subcategory_id is None

    listed = {row.product_id for row in
              await StatisticsRepository(session).least_ordered_products(limit=99)}

    assert legacy.id in listed, "no brand is not a reason to hide a product"
    assert stranded.id not in listed, "its category is deactivated"


# ================================================================ empty shop


@pytest.mark.asyncio
async def test_an_empty_shop_reports_zeros(session: AsyncSession) -> None:
    collected = await StatisticsService(session).collect(NOW)

    assert collected.general == type(collected.general)()
    for period in (
        collected.all_time,
        collected.current_month,
        collected.previous_month,
    ):
        assert period.orders.total == 0
        assert period.orders.completed == 0
        assert period.orders.cancelled == 0
        assert period.revenue == Decimal("0")
    assert collected.most_ordered == []
    assert collected.least_ordered == []


@pytest.mark.asyncio
async def test_a_shop_with_no_completed_orders_still_ranks(
    session: AsyncSession,
) -> None:
    """Every product at zero: the bottom list must fill, the top must stay empty."""
    admin = AdminService(session)
    category = await admin.create_category("C")
    await session.flush()
    for name in ("a", "b", "c", "d"):
        await admin.create_product(
            category_id=category.id,
            name_ru=name, name_en=name, name_de=name, name_uk=name,
            description_ru="d", description_en="d",
            description_de="d", description_uk="d",
            flavor="f", volume="30ml", nicotine_strength="3mg",
            price=Decimal("10.00"),
        )
    await session.flush()

    collected = await StatisticsService(session).collect(NOW)

    assert collected.most_ordered == []
    assert names(collected.least_ordered) == [("a", 0), ("b", 0), ("c", 0)]


# =============================================================== aggregation


def _select_recorder(sink: list[str]):  # type: ignore[no-untyped-def]
    def listener(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            sink.append(statement)

    return listener


@pytest.mark.asyncio
async def test_every_figure_is_aggregated_in_sql(
    session: AsyncSession, shop: Shop
) -> None:
    """The dashboard must not stream order history into the bot process."""
    statements: list[str] = []
    engine = session.get_bind()
    listener = _select_recorder(statements)

    event.listen(engine, "before_cursor_execute", listener)
    try:
        collected = await StatisticsService(session).collect(NOW)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert collected.all_time.orders.total == 18
    assert len(statements) <= 10, f"{len(statements)} queries for one dashboard"
    assert all(
        any(token in sql.upper() for token in ("COUNT(", "SUM("))
        for sql in statements
    ), "a statistic was computed by reading rows"


@pytest.mark.asyncio
async def test_query_count_is_independent_of_history_size(
    session: AsyncSession, shop: Shop
) -> None:
    async def measure() -> int:
        statements: list[str] = []
        engine = session.get_bind()
        listener = _select_recorder(statements)
        event.listen(engine, "before_cursor_execute", listener)
        try:
            await StatisticsService(session).collect(NOW)
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return len(statements)

    small = await measure()

    for index in range(40):
        order = Order(
            user_id=shop.orders["aug-multi-qty"].user_id, customer_name="QA",
            city="berlin", delivery_type="pickup", address="X",
            preferred_time="18:00", phone=None, total_price=Decimal("10.00"),
            status=OrderStatus.COMPLETED, payment_method=PaymentMethod.CASH,
            created_at=at(8, 12, 0, index % 60),
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderItem(
                order_id=order.id, product_id=shop.products["void"].id,
                quantity=1, price=Decimal("10.00"),
            )
        )
    await session.flush()

    assert await measure() == small, "query count must not grow with order volume"
