"""
One enumerated shop, shared by the statistics service tests and the dashboard
tests that render it.

Kept as data rather than as per-test setup so every expected figure can be
recomputed by reading the tables below. The clock is frozen at :data:`NOW`;
nothing here reads the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Subcategory
from app.models.enums import OrderStatus, PaymentMethod
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.repositories.statistics import ProductPopularity
from app.services.admin import AdminService
from app.services.statistics import ShopStatistics, StatisticsService
from tests.factories import make_user

BERLIN = ZoneInfo("Europe/Berlin")

# Frozen clock. August 2026 is the current month, July 2026 the previous one.
NOW = datetime(2026, 8, 19, 12, 0, tzinfo=BERLIN)
JULY_START = datetime(2026, 7, 1, 0, 0, tzinfo=BERLIN)
AUGUST_START = datetime(2026, 8, 1, 0, 0, tzinfo=BERLIN)
SEPTEMBER_START = datetime(2026, 9, 1, 0, 0, tzinfo=BERLIN)


def at(month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    """A moment in 2026, Berlin time."""
    return datetime(2026, month, day, hour, minute, tzinfo=BERLIN)


# --- the catalog -------------------------------------------------------------
# (key, is_active, placement). Creation order fixes the ids, which is what breaks
# ties in the popularity lists. The three placements isolate the three ways a
# product can be off sale: itself inactive, its brand hidden, its category hidden.
ON_SALE, HIDDEN_BRAND, RETIRED_CATEGORY = "on-sale", "hidden-brand", "retired-category"

PRODUCTS: tuple[tuple[str, bool, str], ...] = (
    ("mango", True, ON_SALE),             # in many completed orders
    ("berry", True, ON_SALE),             # in several, one twice across two lines
    ("ice", True, ON_SALE),               # in exactly one completed order
    ("mint", True, ON_SALE),              # only in cancelled / new -> zero completed
    ("void", True, ON_SALE),              # never in any order at all
    ("ghost", False, ON_SALE),            # inactive product, parents both visible
    ("shelved", True, HIDDEN_BRAND),      # active, but its brand is deactivated
    ("archived", True, RETIRED_CATEGORY),  # active, but its category is deactivated
)

# --- the orders --------------------------------------------------------------
# (label, created_at, status, total_price, [(product, quantity), ...])
Line = tuple[str, int]
OrderSpec = tuple[str, datetime, OrderStatus, str, list[Line]]

ORDERS: tuple[OrderSpec, ...] = (
    # ---- older than the previous month
    ("jun-last-minute", at(6, 30, 23, 59), OrderStatus.COMPLETED, "3.00", [("mango", 1)]),
    ("mar-completed", at(3, 3), OrderStatus.COMPLETED, "25.00", [("mango", 1)]),
    ("mar-cancelled", at(3, 4), OrderStatus.CANCELLED, "5.00", [("ice", 1)]),
    # ---- previous month (July)
    ("jul-first-instant", at(7, 1, 0, 0), OrderStatus.COMPLETED, "2.00", [("berry", 1)]),
    ("jul-completed", at(7, 10), OrderStatus.COMPLETED, "30.00", [("mango", 1)]),
    # the same product on two lines of one order: one distinct order, five units
    ("jul-two-lines", at(7, 12), OrderStatus.COMPLETED, "50.00", [("berry", 2), ("berry", 3)]),
    ("jul-cancelled", at(7, 15), OrderStatus.CANCELLED, "90.00", [("mint", 1)]),
    ("jul-new", at(7, 16), OrderStatus.NEW, "15.00", [("ice", 1)]),
    ("jul-last-minute", at(7, 31, 23, 59), OrderStatus.COMPLETED, "1.00", [("berry", 1)]),
    # ---- current month (August)
    ("aug-first-instant", at(8, 1, 0, 0), OrderStatus.COMPLETED, "10.00", [("mango", 1)]),
    # multiple quantities of one product on a single line
    ("aug-multi-qty", at(8, 5), OrderStatus.COMPLETED, "20.00", [("mango", 2)]),
    ("aug-two-products", at(8, 6), OrderStatus.COMPLETED, "40.00", [("berry", 1), ("ice", 1)]),
    ("aug-accepted", at(8, 7), OrderStatus.ACCEPTED, "70.00", [("mango", 1)]),
    ("aug-shipped", at(8, 8), OrderStatus.SHIPPED, "80.00", [("berry", 1)]),
    ("aug-new", at(8, 9), OrderStatus.NEW, "60.00", [("mint", 1)]),
    ("aug-cancelled", at(8, 10), OrderStatus.CANCELLED, "100.00", [("mint", 5)]),
    # both sold, both off sale: they must not reach either popularity list
    ("aug-hidden-brand", at(8, 11), OrderStatus.COMPLETED, "5.00", [("shelved", 1)]),
    ("aug-retired-cat", at(8, 12), OrderStatus.COMPLETED, "7.00", [("archived", 1)]),
)

# ---------------------------------------------------------------------------
# Expected values, recomputed by hand from the two tables above.
#
#   period      total  completed  cancelled  other   completed revenue
#   all time      18      11          3        4   3+25+2+30+50+1+10+20+40+5+7 = 193.00
#   August         9       5          1        3            10+20+40+5+7       =  82.00
#   July           6       4          1        1            2+30+50+1          =  83.00
#
#   distinct completed orders per product        count   on sale?
#   mango     jun-last-minute, mar-completed, jul-completed,
#             aug-first-instant, aug-multi-qty       5    yes
#   berry     jul-first-instant, jul-two-lines,
#             jul-last-minute, aug-two-products      4    yes
#   ice       aug-two-products                       1    yes
#   mint      none: its orders are cancelled / new   0    yes
#   void      none                                   0    yes
#   ghost     none                                   0    no  - product inactive
#   shelved   aug-hidden-brand                       1    no  - brand deactivated
#   archived  aug-retired-cat                        1    no  - category deactivated
#
#   Only the five on-sale products are ranked, so:
#     top 3    = mango 5, berry 4, ice 1
#     bottom 3 = mint 0, void 0, ice 1   (mint/void tie breaks on id)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Shop:
    """Handles onto the seeded rows, so assertions can name things."""

    products: dict[str, Product]
    orders: dict[str, Order]
    active_category: Category
    disabled_category: Category
    active_subcategory: Subcategory


@pytest_asyncio.fixture
async def shop(session: AsyncSession) -> Shop:
    """The whole dataset described by PRODUCTS and ORDERS."""
    admin = AdminService(session)

    active_category = await admin.create_category("Liquids")
    disabled_category = await admin.create_category("Retired")
    await admin.set_category_active(disabled_category, False)
    active_subcategory = await admin.create_subcategory(
        category_id=active_category.id, name="Brand A"
    )
    hidden_subcategory = await admin.create_subcategory(
        category_id=active_category.id, name="Brand B"
    )
    await admin.set_subcategory_active(hidden_subcategory, False)
    retired_subcategory = await admin.create_subcategory(
        category_id=disabled_category.id, name="Brand C"
    )
    await session.flush()

    placements = {
        ON_SALE: (active_category, active_subcategory),
        HIDDEN_BRAND: (active_category, hidden_subcategory),
        RETIRED_CATEGORY: (disabled_category, retired_subcategory),
    }

    products: dict[str, Product] = {}
    for key, is_active, placement in PRODUCTS:
        category, subcategory = placements[placement]
        products[key] = await admin.create_product(
            category_id=category.id,
            subcategory_id=subcategory.id,
            name_ru=key, name_en=key, name_de=key, name_uk=key,
            description_ru="d", description_en="d",
            description_de="d", description_uk="d",
            flavor="f", volume="30ml", nicotine_strength="3mg",
            price=Decimal("10.00"),
            is_active=is_active,
        )
    await session.flush()

    buyer = await make_user(session, telegram_id=30_001)
    await make_user(session, telegram_id=30_002)
    await make_user(session, telegram_id=30_003)
    await session.flush()

    orders: dict[str, Order] = {}
    for label, when, status, total, lines in ORDERS:
        order = Order(
            user_id=buyer.id, customer_name="QA", city="berlin",
            delivery_type="pickup", address="X", preferred_time="18:00",
            phone=None, total_price=Decimal(total), status=status,
            payment_method=PaymentMethod.CASH, created_at=when,
        )
        session.add(order)
        await session.flush()
        for product_key, quantity in lines:
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=products[product_key].id,
                    quantity=quantity,
                    price=Decimal("10.00"),
                )
            )
        orders[label] = order
    await session.flush()

    return Shop(
        products=products,
        orders=orders,
        active_category=active_category,
        disabled_category=disabled_category,
        active_subcategory=active_subcategory,
    )


@pytest_asyncio.fixture
async def stats(session: AsyncSession, shop: Shop) -> ShopStatistics:
    """The dashboard as of the frozen clock."""
    return await StatisticsService(session).collect(NOW)


def names(rows: list[ProductPopularity]) -> list[tuple[str, int]]:
    return [(row.name_en, row.order_count) for row in rows]
