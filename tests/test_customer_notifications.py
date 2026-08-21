"""Customer order-status notifications: content, language, failure isolation."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CityChoice, LanguageCode, OrderStatus, PaymentMethod
from app.models.order import Order
from app.repositories.order import OrderRepository
from app.services.admin import AdminService
from app.services.cart import CartService
from app.services.customer_notification import (
    STATUS_MESSAGE_KEYS,
    CustomerOrderNotificationService,
    is_notifiable,
)
from app.services.localization import LocalizationService
from app.services.order import OrderService
from tests.factories import make_category, make_product, make_user

LANGS = ("ru", "en", "de", "uk")
NOTIFIED = (
    OrderStatus.ACCEPTED,
    OrderStatus.SHIPPED,
    OrderStatus.COMPLETED,
    OrderStatus.CANCELLED,
)


class FakeBot:
    """Records send_message calls; optionally raises a configured error."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)
        if self.error is not None:
            raise self.error


def _bad_request(msg: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=None, message=msg)  # type: ignore[arg-type]


async def _order(
    session: AsyncSession, telegram_id: int, language: LanguageCode = LanguageCode.EN
) -> tuple[Order, Any]:
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
    await session.flush()
    return order, user


# ============================================================ which statuses


def test_exactly_the_four_required_statuses_notify() -> None:
    assert set(STATUS_MESSAGE_KEYS) == set(NOTIFIED)
    for status in NOTIFIED:
        assert is_notifiable(status)
    assert not is_notifiable(OrderStatus.NEW)


@pytest.mark.asyncio
async def test_reopening_does_not_notify(session: AsyncSession) -> None:
    """Cancelled -> New is an internal correction, not customer news."""
    order, user = await _order(session, 12_000)
    await OrderRepository(session).update_status(order, OrderStatus.NEW)
    await session.flush()

    bot = FakeBot()
    sent = await CustomerOrderNotificationService(bot).notify_status_change(order, user)

    assert sent is False
    assert bot.sent == []


# ================================================================== content


@pytest.mark.parametrize("status", NOTIFIED)
@pytest.mark.asyncio
async def test_notification_names_the_order_and_status(
    session: AsyncSession, status: OrderStatus
) -> None:
    order, user = await _order(session, 12_100 + NOTIFIED.index(status))
    await OrderRepository(session).update_status(order, status)
    await session.flush()

    bot = FakeBot()
    assert await CustomerOrderNotificationService(bot).notify_status_change(order, user)

    assert len(bot.sent) == 1
    call = bot.sent[0]
    assert call["chat_id"] == user.telegram_id
    assert f"#{order.id}" in call["text"]
    expected = LocalizationService.from_user(user).t(STATUS_MESSAGE_KEYS[status], order_id=order.id)
    assert call["text"] == expected
    assert "{" not in call["text"]


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.asyncio
async def test_notification_uses_the_persisted_language(
    session: AsyncSession, language: str
) -> None:
    order, user = await _order(session, 12_200 + LANGS.index(language), LanguageCode(language))
    await OrderRepository(session).update_status(order, OrderStatus.SHIPPED)
    await session.flush()

    bot = FakeBot()
    await CustomerOrderNotificationService(bot).notify_status_change(order, user)

    expected = LocalizationService.from_code(language).t(
        "notification.status_shipped", order_id=order.id
    )
    assert bot.sent[0]["text"] == expected
    # and it is genuinely that language, not a fallback to English
    if language != "en":
        assert bot.sent[0]["text"] != LocalizationService.from_code("en").t(
            "notification.status_shipped", order_id=order.id
        )


def test_every_status_message_is_translated_in_all_four_languages() -> None:
    for key in STATUS_MESSAGE_KEYS.values():
        rendered = {LocalizationService.from_code(c).t(key, order_id=7) for c in LANGS}
        assert len(rendered) == len(LANGS), key
        for text in rendered:
            assert "#7" in text
            assert "{" not in text


@pytest.mark.asyncio
async def test_user_without_a_language_falls_back(session: AsyncSession) -> None:
    order, user = await _order(session, 12_300)
    user.language = None
    await OrderRepository(session).update_status(order, OrderStatus.COMPLETED)
    await session.flush()

    bot = FakeBot()
    assert await CustomerOrderNotificationService(bot).notify_status_change(order, user)
    assert f"#{order.id}" in bot.sent[0]["text"]


# ======================================================= failures isolated


@pytest.mark.parametrize(
    "error",
    [
        TelegramForbiddenError(method=None, message="bot was blocked by the user"),  # type: ignore[arg-type]
        TelegramForbiddenError(method=None, message="user is deactivated"),  # type: ignore[arg-type]
        _bad_request("chat not found"),
        TelegramRetryAfter(method=None, message="flood", retry_after=5),  # type: ignore[arg-type,call-arg]
        TelegramNetworkError(method=None, message="timeout"),  # type: ignore[arg-type]
        RuntimeError("unexpected"),
    ],
)
@pytest.mark.asyncio
async def test_delivery_failures_never_raise(session: AsyncSession, error: Exception) -> None:
    """Any failure must be swallowed: the status change is already committed."""
    order, user = await _order(session, 12_400)
    await OrderRepository(session).update_status(order, OrderStatus.SHIPPED)
    await session.flush()

    bot = FakeBot(error=error)
    delivered = await CustomerOrderNotificationService(bot).notify_status_change(order, user)

    assert delivered is False


@pytest.mark.asyncio
async def test_blocked_user_is_logged_as_information_not_an_error(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    order, user = await _order(session, 12_500)
    await OrderRepository(session).update_status(order, OrderStatus.CANCELLED)
    await session.flush()

    bot = FakeBot(
        error=TelegramForbiddenError(method=None, message="bot was blocked")  # type: ignore[arg-type]
    )
    with caplog.at_level(logging.INFO):
        await CustomerOrderNotificationService(bot).notify_status_change(order, user)

    records = [r for r in caplog.records if "blocked" in r.getMessage().lower()]
    assert records, "a blocked user must be logged"
    assert all(r.levelno <= logging.INFO for r in records)


@pytest.mark.asyncio
async def test_unexpected_error_is_logged_with_a_traceback(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    order, user = await _order(session, 12_600)
    await OrderRepository(session).update_status(order, OrderStatus.COMPLETED)
    await session.flush()

    bot = FakeBot(error=RuntimeError("boom"))
    with caplog.at_level(logging.ERROR):
        await CustomerOrderNotificationService(bot).notify_status_change(order, user)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors and any(r.exc_info for r in errors)


@pytest.mark.asyncio
async def test_status_survives_a_failed_notification(
    session: AsyncSession,
) -> None:
    """The database change must stand even when Telegram refuses."""
    admin = AdminService(session)
    order, user = await _order(session, 12_700)

    order = await admin.set_order_status(order, OrderStatus.ACCEPTED)
    await session.commit()  # what the handler does before notifying

    bot = FakeBot(
        error=TelegramForbiddenError(method=None, message="blocked")  # type: ignore[arg-type]
    )
    delivered = await CustomerOrderNotificationService(bot).notify_status_change(order, user)
    assert delivered is False

    session.expunge_all()
    stored = await session.scalar(select(Order.status).where(Order.id == order.id))
    assert stored is OrderStatus.ACCEPTED, "a failed notification rolled back the status"


# ================================================================ no repeats


@pytest.mark.asyncio
async def test_no_notification_when_the_status_does_not_change(
    session: AsyncSession,
) -> None:
    """set_order_status is a no-op for the same status, so nothing is sent."""
    admin = AdminService(session)
    order, user = await _order(session, 12_800)
    order = await admin.set_order_status(order, OrderStatus.ACCEPTED)
    await session.flush()

    bot = FakeBot()
    service = CustomerOrderNotificationService(bot)
    await service.notify_status_change(order, user)
    assert len(bot.sent) == 1

    # the handler returns early on a repeat tap, so no second send happens
    same = await admin.set_order_status(order, OrderStatus.ACCEPTED)
    assert same.status is OrderStatus.ACCEPTED
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_each_real_change_notifies_once(session: AsyncSession) -> None:
    admin = AdminService(session)
    order, user = await _order(session, 12_900)
    bot = FakeBot()
    service = CustomerOrderNotificationService(bot)

    for target in (OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.COMPLETED):
        order = await admin.set_order_status(order, target)
        await session.flush()
        await service.notify_status_change(order, user)

    assert len(bot.sent) == 3
    texts = [c["text"] for c in bot.sent]
    assert all(f"#{order.id}" in t for t in texts)
    assert len(set(texts)) == 3, "each status must have its own wording"
