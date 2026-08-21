"""
The checkout handlers themselves, not just the functions they call.

These exist because of a bug the rest of the suite could not see. Every other
checkout test drove ``build_checkout_summary`` directly, so the *handler* path —
where the acting user is resolved — was never exercised. Picking a payment
method resolved the user from ``callback.message.from_user``, which on a message
the bot itself sent is the **bot**. The bot's cart is empty, so the last step of
checkout told every customer "your cart is empty" and cleared their order.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.handlers.user.checkout import checkout_payment
from app.services.cart import CartService
from app.services.localization import LocalizationService
from app.states.checkout import CheckoutStates
from tests.factories import make_category, make_product, make_user

CUSTOMER_TELEGRAM_ID = 660001
BOT_TELEGRAM_ID = 1  # what Telegram puts in from_user on the bot's own messages

HANDLERS = pathlib.Path(__file__).resolve().parent.parent / "app" / "handlers"


class SpyMessage(Message):
    """A message the *bot* sent: from_user is the bot, exactly as Telegram reports."""

    model_config = {"extra": "allow"}

    async def answer(self, text: str, **kwargs: Any) -> Any:
        self.__dict__.setdefault("sent", []).append(text)
        return self

    async def edit_reply_markup(self, **kwargs: Any) -> Any:
        return self

    @property
    def sent(self) -> list[str]:
        return self.__dict__.setdefault("sent", [])


class SpyCallback(CallbackQuery):
    model_config = {"extra": "allow"}

    async def answer(self, text: str | None = None, **kwargs: Any) -> Any:
        self.__dict__.setdefault("answers", []).append(text)
        return True


def bot_message(chat_id: int) -> SpyMessage:
    return SpyMessage(
        message_id=99,
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type="private"),
        # the bot, not the customer — this is the whole point
        from_user=TgUser(id=BOT_TELEGRAM_ID, is_bot=True, first_name="VShop"),
        text="Choose a payment method",
    )


async def ready_to_pay(
    session: AsyncSession, *, payment: str = "card"
) -> tuple[SpyCallback, FSMContext]:
    """A customer who has filled in checkout and is about to pick a payment method."""
    category = await make_category(session, name="Liquids")
    product = await make_product(session, category, name_en="Mango Ice", price="12.50")
    user = await make_user(session, telegram_id=CUSTOMER_TELEGRAM_ID)
    await session.flush()
    await CartService(session).add_product(user.id, product, quantity=2)
    await session.flush()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(
            bot_id=BOT_TELEGRAM_ID,
            chat_id=CUSTOMER_TELEGRAM_ID,
            user_id=CUSTOMER_TELEGRAM_ID,
        ),
    )
    await state.set_state(CheckoutStates.payment_method)
    await state.update_data(
        customer_name="Clara Schmidt",
        delivery_type="pickup",
        address="Alexanderplatz 1",
        preferred_time="18:00",
        phone="+4915112345678",
    )

    callback = SpyCallback(
        id="cb1",
        from_user=TgUser(id=CUSTOMER_TELEGRAM_ID, is_bot=False, first_name="Clara"),
        chat_instance="ci",
        data=f"checkout:pay:{payment}",
        message=bot_message(CUSTOMER_TELEGRAM_ID),
    )
    return callback, state


@pytest.mark.asyncio
async def test_choosing_a_payment_method_shows_the_order_summary(
    session: AsyncSession,
) -> None:
    """
    Regression: this told the customer their cart was empty and cleared checkout.

    The bug was invisible to a summary-only test, because the summary function
    was never reached — the handler bailed out before calling it.
    """
    callback, state = await ready_to_pay(session)
    i18n = LocalizationService("en")

    await checkout_payment(callback, state, session, i18n)  # type: ignore[arg-type]

    body = "\n".join(callback.message.sent)  # type: ignore[union-attr]
    assert "empty" not in body.lower(), (
        "the customer's cart was resolved as the bot's: " + body[:200]
    )
    assert "Clara Schmidt" in body
    assert "Mango Ice" in body
    assert "25.00" in body, "two units at 12.50 should total 25.00"


@pytest.mark.asyncio
async def test_choosing_a_payment_method_advances_the_state(
    session: AsyncSession,
) -> None:
    """The customer must end up at confirmation, not thrown out of checkout."""
    callback, state = await ready_to_pay(session)

    await checkout_payment(
        callback,
        state,
        session,
        LocalizationService("en"),  # type: ignore[arg-type]
    )

    assert await state.get_state() == CheckoutStates.confirmation.state
    assert (await state.get_data())["payment_method"] == "card"


@pytest.mark.asyncio
async def test_the_payment_choice_is_recorded_before_the_summary(
    session: AsyncSession,
) -> None:
    callback, state = await ready_to_pay(session, payment="cash")

    await checkout_payment(
        callback,
        state,
        session,
        LocalizationService("en"),  # type: ignore[arg-type]
    )

    body = "\n".join(callback.message.sent)  # type: ignore[union-attr]
    assert (await state.get_data())["payment_method"] == "cash"
    assert "cash" in body.lower()


@pytest.mark.asyncio
async def test_the_bot_is_never_registered_as_a_customer(
    session: AsyncSession,
) -> None:
    """
    The old code called ``ensure_user`` with the bot's own ``from_user``.

    That silently created a User row for the bot, which would then collect a
    cart, a language and an order history of its own.
    """
    from sqlalchemy import select

    from app.models.user import User

    callback, state = await ready_to_pay(session)
    await checkout_payment(
        callback,
        state,
        session,
        LocalizationService("en"),  # type: ignore[arg-type]
    )

    ids = set((await session.scalars(select(User.telegram_id))).all())
    assert BOT_TELEGRAM_ID not in ids, "a User row was created for the bot"
    assert CUSTOMER_TELEGRAM_ID in ids


# ------------------------------------------------------- the whole class


def _derives_from_callback_message(node: ast.AST) -> bool:
    return any(
        isinstance(sub, ast.Attribute)
        and sub.attr == "message"
        and isinstance(sub.value, ast.Name)
        and sub.value.id in {"callback", "query", "cb"}
        for sub in ast.walk(node)
    )


def test_no_helper_resolves_the_bot_as_the_acting_user() -> None:
    """
    Guard the whole class, not just the one instance that was found.

    A helper that reads ``<first arg>.from_user`` is asking "who is acting?".
    Handing it ``callback.message`` answers "the bot", because that message was
    sent by the bot. The user must be resolved from ``callback.from_user`` and
    passed in.
    """
    offenders: list[str] = []

    for path in sorted(HANDLERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        risky: dict[str, int] = {}
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not fn.args.args:
                continue
            first = fn.args.args[0].arg
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "from_user"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == first
                ):
                    risky[fn.name] = fn.lineno
                    break
        if not risky:
            continue

        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            tainted: set[str] = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign) and _derives_from_callback_message(node.value):
                    tainted |= {t.id for t in node.targets if isinstance(t, ast.Name)}
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in risky
                    and node.args
                ):
                    arg = node.args[0]
                    if _derives_from_callback_message(arg) or (
                        isinstance(arg, ast.Name) and arg.id in tainted
                    ):
                        offenders.append(
                            f"{path.name}:{node.lineno} {fn.name}() calls "
                            f"{node.func.id}(<the bot's message>) — "
                            f"{node.func.id} reads .from_user at line "
                            f"{risky[node.func.id]}"
                        )

    assert offenders == [], "the bot would be resolved as the acting user: " + "; ".join(offenders)
