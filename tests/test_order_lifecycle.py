"""Order lifecycle: five statuses, safe transitions, admin actions."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.admin_orders import (
    CALLBACK_ORDER_STATUS_PREFIX,
    order_manage_keyboard,
)
from app.models.enums import CityChoice, LanguageCode, OrderStatus, PaymentMethod
from app.models.order import Order
from app.repositories.order import OrderRepository
from app.services.admin import AdminService, InvalidStatusTransitionError
from app.services.cart import CartService
from app.services.localization import LocalizationService
from app.services.order import OrderService
from app.utils.order_status import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    allowed_transitions,
    can_transition,
    is_terminal,
    status_action_label,
    status_code,
    status_from_code,
    status_label,
)
from tests.factories import make_category, make_product, make_user

LANGS = ("ru", "en", "de", "uk")

# The lifecycle, spelled out independently of the implementation.
EXPECTED: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.ACCEPTED, OrderStatus.CANCELLED},
    OrderStatus.ACCEPTED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: {OrderStatus.NEW},  # undo a mis-tapped cancel
}


async def _order(session: AsyncSession, telegram_id: int) -> Order:
    category = await make_category(session, name="Liquids")
    product = await make_product(session, category, name_en="Mango", price="10.00")
    user = await make_user(
        session, telegram_id=telegram_id,
        language=LanguageCode.EN, city=CityChoice.BERLIN,
    )
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=1)
    await session.flush()
    return await OrderService(session).place_order_from_cart(
        user, customer_name="QA", delivery_type="pickup", address="X",
        preferred_time="18:00", phone=None, payment_method=PaymentMethod.CASH,
    )


def _buttons(markup):  # type: ignore[no-untyped-def]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


# ================================================================= statuses


def test_five_statuses_in_lifecycle_order() -> None:
    assert [s.value for s in OrderStatus] == [
        "New", "Accepted", "Shipped", "Completed", "Cancelled",
    ]


def test_shipped_round_trips_through_its_callback_code() -> None:
    assert status_code(OrderStatus.SHIPPED) == "shipped"
    assert status_from_code("shipped") is OrderStatus.SHIPPED
    assert status_from_code("nonsense") is None


@pytest.mark.parametrize("language", LANGS)
def test_every_status_has_a_label(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    for status in OrderStatus:
        label = status_label(i18n, status)
        assert label and label != str(status)
        assert not label.startswith("admin.")


@pytest.mark.parametrize("language", LANGS)
def test_shipped_label_is_translated(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    assert i18n.t("admin.order_status_shipped").startswith("📦")
    rendered = {
        LocalizationService.from_code(c).t("admin.order_status_shipped")
        for c in LANGS
    }
    assert len(rendered) == len(LANGS)


# ============================================================== transitions


@pytest.mark.parametrize("current", list(OrderStatus))
def test_allowed_transitions_match_the_lifecycle(current: OrderStatus) -> None:
    assert set(allowed_transitions(current)) == EXPECTED[current]


@pytest.mark.parametrize("current", list(OrderStatus))
@pytest.mark.parametrize("target", list(OrderStatus))
def test_full_transition_matrix(current: OrderStatus, target: OrderStatus) -> None:
    """All 25 pairs, checked against the table written out above."""
    assert can_transition(current, target) is (target in EXPECTED[current])


def test_terminal_states_are_dead_ends() -> None:
    assert TERMINAL_STATUSES == {OrderStatus.COMPLETED}
    assert ACTIVE_STATUSES == {
        OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.SHIPPED,
    }
    for status in TERMINAL_STATUSES:
        assert is_terminal(status)
        assert allowed_transitions(status) == ()


def test_no_status_can_move_to_itself() -> None:
    for status in OrderStatus:
        assert not can_transition(status, status)


def test_the_happy_path_is_linear() -> None:
    chain = [
        OrderStatus.NEW, OrderStatus.ACCEPTED,
        OrderStatus.SHIPPED, OrderStatus.COMPLETED,
    ]
    for current, target in zip(chain, chain[1:], strict=False):
        assert can_transition(current, target)
    # ...and never skips a step
    assert not can_transition(OrderStatus.NEW, OrderStatus.SHIPPED)
    assert not can_transition(OrderStatus.NEW, OrderStatus.COMPLETED)
    assert not can_transition(OrderStatus.ACCEPTED, OrderStatus.COMPLETED)


def test_cancellation_only_from_active_states() -> None:
    for status in ACTIVE_STATUSES:
        assert can_transition(status, OrderStatus.CANCELLED)
    assert not can_transition(OrderStatus.COMPLETED, OrderStatus.CANCELLED)


def test_completed_orders_cannot_be_reopened() -> None:
    """Completed is final: revenue and customer notifications depend on it."""
    for target in OrderStatus:
        assert not can_transition(OrderStatus.COMPLETED, target)


def test_cancelled_can_be_undone_back_to_new() -> None:
    """A mis-tapped cancel is recoverable, but only back to the start."""
    assert can_transition(OrderStatus.CANCELLED, OrderStatus.NEW)
    for target in (OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.COMPLETED):
        assert not can_transition(OrderStatus.CANCELLED, target), target


def test_cancelled_is_not_treated_as_an_active_order() -> None:
    """It has an undo path, but it is not in the fulfilment pipeline."""
    assert OrderStatus.CANCELLED not in ACTIVE_STATUSES


# ============================================================ service guard


@pytest.mark.asyncio
async def test_walking_the_whole_lifecycle(session: AsyncSession) -> None:
    admin = AdminService(session)
    order = await _order(session, 11_000)
    await session.flush()
    assert order.status is OrderStatus.NEW

    for target in (OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.COMPLETED):
        order = await admin.set_order_status(order, target)
        await session.flush()
        assert order.status is target

    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is OrderStatus.COMPLETED


@pytest.mark.parametrize(
    "start,forbidden",
    [
        (OrderStatus.NEW, OrderStatus.SHIPPED),
        (OrderStatus.NEW, OrderStatus.COMPLETED),
        (OrderStatus.ACCEPTED, OrderStatus.COMPLETED),
        (OrderStatus.COMPLETED, OrderStatus.NEW),
        (OrderStatus.COMPLETED, OrderStatus.CANCELLED),
        (OrderStatus.CANCELLED, OrderStatus.ACCEPTED),
    ],
)
@pytest.mark.asyncio
async def test_invalid_transitions_are_refused(
    session: AsyncSession, start: OrderStatus, forbidden: OrderStatus
) -> None:
    admin = AdminService(session)
    order = await _order(session, 11_100 + list(OrderStatus).index(forbidden))
    await session.flush()
    await OrderRepository(session).update_status(order, start)
    await session.flush()

    with pytest.raises(InvalidStatusTransitionError):
        await admin.set_order_status(order, forbidden)

    # the refusal must leave the order exactly as it was
    assert order.status is start
    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is start


@pytest.mark.asyncio
async def test_setting_the_same_status_is_a_no_op(session: AsyncSession) -> None:
    admin = AdminService(session)
    order = await _order(session, 11_200)
    await session.flush()

    same = await admin.set_order_status(order, OrderStatus.NEW)
    assert same.status is OrderStatus.NEW


@pytest.mark.asyncio
async def test_cancel_from_each_active_state(session: AsyncSession) -> None:
    admin = AdminService(session)
    for index, start in enumerate(
        (OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.SHIPPED)
    ):
        order = await _order(session, 11_300 + index)
        await session.flush()
        await OrderRepository(session).update_status(order, start)
        await session.flush()

        order = await admin.set_order_status(order, OrderStatus.CANCELLED)
        await session.flush()
        assert order.status is OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_allowed_next_statuses_helper(session: AsyncSession) -> None:
    admin = AdminService(session)
    order = await _order(session, 11_400)
    await session.flush()

    assert admin.allowed_next_statuses(order) == (
        OrderStatus.ACCEPTED, OrderStatus.CANCELLED,
    )
    order = await admin.set_order_status(order, OrderStatus.ACCEPTED)
    assert admin.allowed_next_statuses(order) == (
        OrderStatus.SHIPPED, OrderStatus.CANCELLED,
    )


@pytest.mark.asyncio
async def test_repository_ship_helper(session: AsyncSession) -> None:
    order = await _order(session, 11_500)
    await session.flush()
    repo = OrderRepository(session)
    await repo.accept(order)
    await repo.ship(order)
    await session.flush()

    assert order.status is OrderStatus.SHIPPED


# ================================================================ admin UI


@pytest.mark.parametrize("current", list(OrderStatus))
def test_keyboard_offers_only_legal_moves(current: OrderStatus) -> None:
    i18n = LocalizationService.from_code("en")
    order = type("O", (), {"id": 7, "status": current})()
    payloads = [
        data
        for _, data in _buttons(order_manage_keyboard(i18n, order, list_kind="new", page=0))  # type: ignore[arg-type]
        if data.startswith(CALLBACK_ORDER_STATUS_PREFIX)
    ]
    offered = {
        p.removeprefix(CALLBACK_ORDER_STATUS_PREFIX).split(":")[1]
        for p in payloads
    }

    assert offered == {status_code(s) for s in EXPECTED[current]}


def test_completed_orders_show_no_status_buttons() -> None:
    i18n = LocalizationService.from_code("en")
    order = type("O", (), {"id": 7, "status": OrderStatus.COMPLETED})()
    entries = _buttons(order_manage_keyboard(i18n, order, list_kind="done", page=0))  # type: ignore[arg-type]

    assert not any(
        data.startswith(CALLBACK_ORDER_STATUS_PREFIX) for _, data in entries
    )
    assert len(entries) == 1  # only Back


@pytest.mark.parametrize("language", LANGS)
def test_cancelled_orders_offer_a_reopen_button(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    order = type("O", (), {"id": 7, "status": OrderStatus.CANCELLED})()
    entries = _buttons(order_manage_keyboard(i18n, order, list_kind="done", page=0))  # type: ignore[arg-type]

    actions = [
        (text, data)
        for text, data in entries
        if data.startswith(CALLBACK_ORDER_STATUS_PREFIX)
    ]
    assert len(actions) == 1
    label, payload = actions[0]
    assert payload.removeprefix(CALLBACK_ORDER_STATUS_PREFIX).split(":")[1] == "new"
    assert label == i18n.t("admin.order_action_reopen")
    assert label.startswith("↩️")


@pytest.mark.parametrize("language", LANGS)
def test_mark_as_shipped_action_is_offered_and_localized(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    order = type("O", (), {"id": 7, "status": OrderStatus.ACCEPTED})()
    labels = [
        text
        for text, data in _buttons(
            order_manage_keyboard(i18n, order, list_kind="new", page=0)  # type: ignore[arg-type]
        )
        if data.startswith(CALLBACK_ORDER_STATUS_PREFIX)
    ]

    ship = status_action_label(i18n, OrderStatus.SHIPPED)
    assert ship in labels
    assert ship.startswith("📦")
    assert ship == i18n.t("admin.order_action_ship")


def test_action_labels_differ_per_language() -> None:
    for key in ("admin.order_action_ship", "admin.order_action_accept",
                "admin.order_action_complete", "admin.order_action_cancel"):
        rendered = {LocalizationService.from_code(c).t(key) for c in LANGS}
        assert len(rendered) == len(LANGS), key


@pytest.mark.parametrize("language", LANGS)
def test_invalid_transition_message_is_localized(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    text = i18n.t(
        "admin.order_invalid_transition",
        current=status_label(i18n, OrderStatus.COMPLETED),
        target=status_label(i18n, OrderStatus.NEW),
    )
    assert "{" not in text
    assert status_label(i18n, OrderStatus.COMPLETED) in text


# ================================================== existing flow unaffected


@pytest.mark.asyncio
async def test_new_orders_are_still_created_as_new(session: AsyncSession) -> None:
    order = await _order(session, 11_600)
    await session.flush()

    assert order.status is OrderStatus.NEW
    assert order.total_price == Decimal("10.00")
    assert order.payment_method is PaymentMethod.CASH


@pytest.mark.asyncio
async def test_existing_status_listings_still_work(session: AsyncSession) -> None:
    """The admin New/Completed lists predate Shipped and must be unaffected."""
    admin = AdminService(session)
    order = await _order(session, 11_700)
    await session.flush()

    assert await admin.count_orders_by_status(OrderStatus.NEW) == 1
    assert await admin.count_orders_by_status(OrderStatus.SHIPPED) == 0

    order = await admin.set_order_status(order, OrderStatus.ACCEPTED)
    order = await admin.set_order_status(order, OrderStatus.SHIPPED)
    await session.flush()

    assert await admin.count_orders_by_status(OrderStatus.NEW) == 0
    assert await admin.count_orders_by_status(OrderStatus.SHIPPED) == 1
    listed = await admin.list_orders_by_status(OrderStatus.SHIPPED)
    assert [o.id for o in listed] == [order.id]


@pytest.mark.asyncio
async def test_reopening_a_cancelled_order(session: AsyncSession) -> None:
    """Cancel by mistake, undo, then fulfil normally."""
    admin = AdminService(session)
    order = await _order(session, 11_800)
    await session.flush()

    order = await admin.set_order_status(order, OrderStatus.CANCELLED)
    await session.flush()
    assert order.status is OrderStatus.CANCELLED

    order = await admin.set_order_status(order, OrderStatus.NEW)
    await session.flush()
    assert order.status is OrderStatus.NEW
    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is OrderStatus.NEW

    # and the normal pipeline still works from there
    for target in (OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.COMPLETED):
        order = await admin.set_order_status(order, target)
    await session.flush()
    assert order.status is OrderStatus.COMPLETED


@pytest.mark.asyncio
async def test_reopening_never_skips_to_the_middle(session: AsyncSession) -> None:
    admin = AdminService(session)
    order = await _order(session, 11_900)
    await session.flush()
    order = await admin.set_order_status(order, OrderStatus.CANCELLED)
    await session.flush()

    for forbidden in (OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.COMPLETED):
        with pytest.raises(InvalidStatusTransitionError):
            await admin.set_order_status(order, forbidden)
        assert order.status is OrderStatus.CANCELLED
