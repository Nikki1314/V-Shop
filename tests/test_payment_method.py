"""Preferred payment method: capture, storage, and every place it surfaces."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.handlers.user.checkout import build_checkout_summary
from app.keyboards.checkout import CALLBACK_PAYMENT_PREFIX, payment_keyboard
from app.models.enums import CityChoice, LanguageCode, OrderStatus, PaymentMethod
from app.models.order import Order
from app.services.cart import CartService
from app.services.localization import LocalizationService
from app.services.notification import OrderNotificationService
from app.services.order import OrderService
from app.states.checkout import CheckoutStates
from app.utils.admin_order import format_admin_order_card
from app.utils.labels import payment_label, payment_label_en
from tests.factories import make_category, make_product, make_user

LANGS = ("ru", "en", "de", "uk")


def _buttons(markup):  # type: ignore[no-untyped-def]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def _ready_cart(session: AsyncSession, telegram_id: int):  # type: ignore[no-untyped-def]
    category = await make_category(session, name="Liquids")
    product = await make_product(session, category, name_en="Mango", price="18.00")
    user = await make_user(
        session, telegram_id=telegram_id,
        language=LanguageCode.EN, city=CityChoice.BERLIN,
    )
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=1)
    await session.flush()
    return user, product


# ---------------------------------------------------------------- FSM step


def test_payment_step_sits_between_contact_and_confirmation() -> None:
    states = [s.state.split(":")[-1] for s in CheckoutStates.__all_states__]
    assert states.index("contact") < states.index("payment_method")
    assert states.index("payment_method") < states.index("confirmation")


@pytest.mark.parametrize("language", LANGS)
def test_payment_keyboard_offers_cash_and_card(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    entries = _buttons(payment_keyboard(i18n))

    assert entries[0] == (
        i18n.t("checkout.payment_cash"),
        f"{CALLBACK_PAYMENT_PREFIX}cash",
    )
    assert entries[1] == (
        i18n.t("checkout.payment_card"),
        f"{CALLBACK_PAYMENT_PREFIX}card",
    )
    assert entries[0][0].startswith("💵")
    assert entries[1][0].startswith("💳")


def test_payment_callbacks_parse_back_to_the_enum() -> None:
    for method in PaymentMethod:
        payload = f"{CALLBACK_PAYMENT_PREFIX}{method.value}"
        assert PaymentMethod(payload.removeprefix(CALLBACK_PAYMENT_PREFIX)) is method
        assert len(payload.encode()) <= 64


def test_payment_labels_are_translated_per_language() -> None:
    """Each language renders its own wording.

    Russian and Ukrainian legitimately share some words ("Оплата" is identical
    in both), so identical ru/uk output is not evidence of a missing
    translation. What must always differ is across script families.
    """
    for key in ("checkout.payment_cash", "checkout.payment_card",
                "checkout.ask_payment", "checkout.summary_payment"):
        rendered = {c: LocalizationService.from_code(c).t(key) for c in LANGS}
        for code, value in rendered.items():
            assert value and not value.startswith("checkout."), f"{key} ({code})"
        assert rendered["en"] != rendered["ru"], key
        assert rendered["en"] != rendered["uk"], key
        assert rendered["de"] != rendered["ru"], key

    # the words that name the methods must differ in every language
    for key in ("checkout.payment_cash", "checkout.payment_card"):
        rendered = {LocalizationService.from_code(c).t(key) for c in LANGS}
        assert len(rendered) == len(LANGS), key


def test_summary_payment_keeps_its_placeholder() -> None:
    for code in LANGS:
        assert "{payment}" in LocalizationService.from_code(code).t(
            "checkout.summary_payment"
        )


# ----------------------------------------------------------------- storage


@pytest.mark.parametrize("method", list(PaymentMethod))
@pytest.mark.asyncio
async def test_payment_method_is_stored_on_the_order(
    session: AsyncSession, method: PaymentMethod
) -> None:
    user, _product = await _ready_cart(session, 9000 + list(PaymentMethod).index(method))

    order = await OrderService(session).place_order_from_cart(
        user,
        customer_name="QA",
        delivery_type="pickup",
        address="Teststr. 1",
        preferred_time="18:00",
        phone=None,
        payment_method=method,
    )
    await session.flush()

    assert order.payment_method is method

    stored = await session.scalar(
        select(Order.payment_method).where(Order.id == order.id)
    )
    assert stored is method
    assert PaymentMethod(stored).value == method.value


@pytest.mark.asyncio
async def test_payment_method_survives_a_reload(session: AsyncSession) -> None:
    user, _product = await _ready_cart(session, 9010)
    order = await OrderService(session).place_order_from_cart(
        user, customer_name="QA", delivery_type="pickup", address="A",
        preferred_time="18:00", phone=None, payment_method=PaymentMethod.CARD,
    )
    order_id = order.id
    await session.flush()
    session.expunge_all()

    reloaded = await session.get(Order, order_id)
    assert reloaded is not None
    assert reloaded.payment_method is PaymentMethod.CARD


# ---------------------------------------------------- appears where required


@pytest.mark.parametrize("language", LANGS)
def test_order_confirmation_summary_shows_payment(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    user = type("U", (), {"selected_city": CityChoice.BERLIN})()
    view = type("V", (), {"lines": [], "total": Decimal("18.00")})()
    data = {
        "customer_name": "QA",
        "delivery_type": "pickup",
        "address": "Teststr. 1",
        "preferred_time": "18:00",
        "phone": None,
        "payment_method": PaymentMethod.CASH.value,
    }

    summary = build_checkout_summary(i18n, data=data, user=user, view=view)  # type: ignore[arg-type]
    assert i18n.t("checkout.payment_cash") in summary


@pytest.mark.asyncio
async def test_manager_notification_shows_payment(session: AsyncSession) -> None:
    user, _product = await _ready_cart(session, 9020)
    order = await OrderService(session).place_order_from_cart(
        user, customer_name="QA", delivery_type="pickup", address="A",
        preferred_time="18:00", phone=None, payment_method=PaymentMethod.CARD,
    )
    await session.flush()

    settings = type("S", (), {"manager_chat_id": -100, "admin_ids": []})()
    text = OrderNotificationService(None, settings).format_new_order_message(  # type: ignore[arg-type]
        order, user
    )
    assert "Payment:" in text
    assert "Card Transfer" in text


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.asyncio
async def test_admin_order_view_shows_payment(
    session: AsyncSession, language: str
) -> None:
    user, _product = await _ready_cart(session, 9030 + LANGS.index(language))
    order = await OrderService(session).place_order_from_cart(
        user, customer_name="QA", delivery_type="pickup", address="A",
        preferred_time="18:00", phone=None, payment_method=PaymentMethod.CASH,
    )
    await session.flush()

    i18n = LocalizationService.from_code(language)
    card = format_admin_order_card(order, i18n)
    assert i18n.t("checkout.payment_cash") in card
    assert "{" not in card


# ------------------------------------------------------------ legacy orders


@pytest.mark.asyncio
async def test_orders_placed_before_the_step_remain_valid(
    session: AsyncSession,
) -> None:
    """The column is nullable, so historical orders keep working untouched."""
    user, _product = await _ready_cart(session, 9040)
    order = await OrderService(session).place_order_from_cart(
        user, customer_name="Legacy", delivery_type="pickup", address="A",
        preferred_time="18:00", phone=None,  # no payment method supplied
    )
    await session.flush()

    assert order.payment_method is None
    assert order.status is OrderStatus.NEW
    assert order.total_price == Decimal("18.00")


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.asyncio
async def test_legacy_order_renders_a_localized_fallback(
    session: AsyncSession, language: str
) -> None:
    user, _product = await _ready_cart(session, 9050 + LANGS.index(language))
    order = await OrderService(session).place_order_from_cart(
        user, customer_name="Legacy", delivery_type="pickup", address="A",
        preferred_time="18:00", phone=None,
    )
    await session.flush()

    i18n = LocalizationService.from_code(language)
    card = format_admin_order_card(order, i18n)
    assert i18n.t("checkout.payment_not_set") in card
    assert "{" not in card
    assert "None" not in card


def test_label_helpers_handle_missing_values() -> None:
    for language in LANGS:
        i18n = LocalizationService.from_code(language)
        assert payment_label(i18n, None) == i18n.t("checkout.payment_not_set")
        assert payment_label(i18n, PaymentMethod.CASH) == i18n.t("checkout.payment_cash")
        assert payment_label(i18n, "cash") == i18n.t("checkout.payment_cash")
        # an unknown stored value degrades to itself rather than crashing
        assert payment_label(i18n, "crypto") == "crypto"

    assert payment_label_en(None) == "—"
    assert payment_label_en(PaymentMethod.CARD) == "Card Transfer"
