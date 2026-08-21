"""Every valid status transition × every language, with its notification.

The admin handler's sequence is: reject a no-op, apply the change, commit, then
notify. :func:`apply_status_change` mirrors that sequence exactly so the matrix
below exercises the same ordering without a dispatcher harness.
"""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CityChoice, LanguageCode, OrderStatus, PaymentMethod
from app.models.order import Order
from app.models.user import User
from app.repositories.order import OrderRepository
from app.services.admin import AdminService
from app.services.cart import CartService
from app.services.customer_notification import (
    STATUS_MESSAGE_KEYS,
    CustomerOrderNotificationService,
)
from app.services.localization import LocalizationService
from app.services.order import OrderService
from app.utils.order_status import can_transition
from tests.factories import make_category, make_product, make_user

LANGS = ("ru", "en", "de", "uk")

# The transitions under verification, exactly as specified.
TRANSITIONS: list[tuple[OrderStatus, OrderStatus]] = [
    (OrderStatus.NEW, OrderStatus.ACCEPTED),
    (OrderStatus.ACCEPTED, OrderStatus.SHIPPED),
    (OrderStatus.SHIPPED, OrderStatus.COMPLETED),
    (OrderStatus.NEW, OrderStatus.CANCELLED),
    (OrderStatus.ACCEPTED, OrderStatus.CANCELLED),
    (OrderStatus.SHIPPED, OrderStatus.CANCELLED),
]
MATRIX = [(src, dst, lang) for src, dst in TRANSITIONS for lang in LANGS]


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)
        if self.error is not None:
            raise self.error


async def _order_at(
    session: AsyncSession,
    telegram_id: int,
    status: OrderStatus,
    language: LanguageCode,
) -> tuple[Order, User]:
    """An order parked at ``status`` with a customer speaking ``language``."""
    category = await make_category(session, name="Liquids")
    product = await make_product(session, category, name_en="Mango", price="10.00")
    user = await make_user(
        session, telegram_id=telegram_id, language=language, city=CityChoice.BERLIN
    )
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=1)
    await session.flush()
    order = await OrderService(session).place_order_from_cart(
        user,
        customer_name="QA",
        delivery_type="pickup",
        address="X",
        preferred_time="18:00",
        phone=None,
        payment_method=PaymentMethod.CASH,
    )
    if status is not OrderStatus.NEW:
        await OrderRepository(session).update_status(order, status)
    await session.flush()
    return order, user


async def apply_status_change(
    session: AsyncSession,
    bot: FakeBot,
    order: Order,
    user: User,
    target: OrderStatus,
) -> bool:
    """Mirror of the admin handler: no-op guard → apply → commit → notify."""
    if order.status == target:
        return False  # handler answers the callback and returns
    await AdminService(session).set_order_status(order, target)
    await session.commit()
    return await CustomerOrderNotificationService(bot).notify_status_change(  # type: ignore[arg-type]
        order, user
    )


# ========================================================= the full matrix


def test_matrix_covers_every_required_transition() -> None:
    assert len(TRANSITIONS) == 6
    assert len(MATRIX) == 24
    for src, dst in TRANSITIONS:
        assert can_transition(src, dst), f"{src} -> {dst} should be legal"
        assert dst in STATUS_MESSAGE_KEYS, f"{dst} should notify"


@pytest.mark.parametrize("source,target,language", MATRIX)
@pytest.mark.asyncio
async def test_transition_notifies_in_the_customers_language(
    session: AsyncSession,
    source: OrderStatus,
    target: OrderStatus,
    language: str,
) -> None:
    order, user = await _order_at(
        session,
        13_000 + MATRIX.index((source, target, language)),
        source,
        LanguageCode(language),
    )
    bot = FakeBot()

    delivered = await apply_status_change(session, bot, order, user, target)

    # the status really moved
    assert delivered is True
    assert order.status is target
    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is target

    # exactly one notification, in the customer's language, naming the order
    assert len(bot.sent) == 1
    call = bot.sent[0]
    assert call["chat_id"] == user.telegram_id
    expected = LocalizationService.from_code(language).t(
        STATUS_MESSAGE_KEYS[target], order_id=order.id
    )
    assert call["text"] == expected
    assert f"#{order.id}" in call["text"]
    assert "{" not in call["text"]


@pytest.mark.parametrize("source,target", TRANSITIONS)
@pytest.mark.asyncio
async def test_each_transition_has_wording_of_its_own(
    session: AsyncSession, source: OrderStatus, target: OrderStatus
) -> None:
    """A customer must be able to tell the statuses apart."""
    texts = {
        LocalizationService.from_code(lang).t(STATUS_MESSAGE_KEYS[target], order_id=1)
        for lang in LANGS
    }
    assert len(texts) == len(LANGS)

    others = {
        LocalizationService.from_code("en").t(key, order_id=1)
        for status, key in STATUS_MESSAGE_KEYS.items()
        if status is not target
    }
    mine = LocalizationService.from_code("en").t(STATUS_MESSAGE_KEYS[target], order_id=1)
    assert mine not in others


# ================================================== unchanged status is quiet


@pytest.mark.parametrize("status", [s for s, _ in TRANSITIONS] + [OrderStatus.COMPLETED])
@pytest.mark.asyncio
async def test_no_notification_when_status_is_unchanged(
    session: AsyncSession, status: OrderStatus
) -> None:
    order, user = await _order_at(session, 13_100 + status.name.__len__(), status, LanguageCode.EN)
    bot = FakeBot()

    delivered = await apply_status_change(session, bot, order, user, status)

    assert delivered is False
    assert bot.sent == []
    assert order.status is status


# ============================================ duplicate callbacks are quiet


@pytest.mark.parametrize("source,target", TRANSITIONS)
@pytest.mark.asyncio
async def test_duplicate_callback_sends_one_notification(
    session: AsyncSession, source: OrderStatus, target: OrderStatus
) -> None:
    """A double tap on the same action must not message the customer twice."""
    order, user = await _order_at(
        session, 13_200 + TRANSITIONS.index((source, target)), source, LanguageCode.RU
    )
    bot = FakeBot()

    first = await apply_status_change(session, bot, order, user, target)
    second = await apply_status_change(session, bot, order, user, target)
    third = await apply_status_change(session, bot, order, user, target)

    assert (first, second, third) == (True, False, False)
    assert len(bot.sent) == 1, "the repeat taps must be silent"
    assert order.status is target


@pytest.mark.asyncio
async def test_walking_the_pipeline_notifies_once_per_step(
    session: AsyncSession,
) -> None:
    order, user = await _order_at(session, 13_300, OrderStatus.NEW, LanguageCode.UK)
    bot = FakeBot()
    steps = (OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.COMPLETED)

    for target in steps:
        assert await apply_status_change(session, bot, order, user, target) is True
        # an immediate repeat of the same step stays silent
        assert await apply_status_change(session, bot, order, user, target) is False

    expected = [
        LocalizationService.from_code("uk").t(STATUS_MESSAGE_KEYS[target], order_id=order.id)
        for target in steps
    ]
    assert [call["text"] for call in bot.sent] == expected


# ==================================== telegram failure never touches the DB


@pytest.mark.parametrize("source,target", TRANSITIONS)
@pytest.mark.asyncio
async def test_delivery_failure_leaves_the_status_applied(
    session: AsyncSession, source: OrderStatus, target: OrderStatus
) -> None:
    order, user = await _order_at(
        session, 13_400 + TRANSITIONS.index((source, target)), source, LanguageCode.DE
    )
    bot = FakeBot(
        error=TelegramForbiddenError(method=None, message="bot was blocked")  # type: ignore[arg-type]
    )

    delivered = await apply_status_change(session, bot, order, user, target)

    assert delivered is False
    assert order.status is target
    session.expunge_all()
    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is target, "a failed notification must not undo the status change"


@pytest.mark.parametrize(
    "error",
    [
        TelegramForbiddenError(method=None, message="bot was blocked by the user"),  # type: ignore[arg-type]
        TelegramForbiddenError(method=None, message="user is deactivated"),  # type: ignore[arg-type]
        TelegramBadRequest(method=None, message="chat not found"),  # type: ignore[arg-type]
        RuntimeError("transport exploded"),
    ],
)
@pytest.mark.asyncio
async def test_every_failure_mode_keeps_the_change(session: AsyncSession, error: Exception) -> None:
    order, user = await _order_at(session, 13_500, OrderStatus.ACCEPTED, LanguageCode.EN)
    bot = FakeBot(error=error)

    delivered = await apply_status_change(session, bot, order, user, OrderStatus.SHIPPED)

    assert delivered is False
    session.expunge_all()
    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is OrderStatus.SHIPPED


@pytest.mark.asyncio
async def test_a_blocked_customer_does_not_stop_the_next_order(
    session: AsyncSession,
) -> None:
    """One unreachable customer must not break processing for everyone else."""
    blocked_order, blocked_user = await _order_at(session, 13_600, OrderStatus.NEW, LanguageCode.EN)
    ok_order, ok_user = await _order_at(session, 13_601, OrderStatus.NEW, LanguageCode.RU)

    failing = FakeBot(
        error=TelegramForbiddenError(method=None, message="blocked")  # type: ignore[arg-type]
    )
    working = FakeBot()

    assert (
        await apply_status_change(
            session, failing, blocked_order, blocked_user, OrderStatus.ACCEPTED
        )
        is False
    )
    assert (
        await apply_status_change(session, working, ok_order, ok_user, OrderStatus.ACCEPTED) is True
    )

    assert blocked_order.status is OrderStatus.ACCEPTED
    assert ok_order.status is OrderStatus.ACCEPTED
    assert len(working.sent) == 1
