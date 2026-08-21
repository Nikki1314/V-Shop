"""Private-chat isolation: only one-to-one chats reach the handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update, User

from app.middlewares import setup_middlewares
from app.middlewares.database import DatabaseMiddleware
from app.middlewares.private_chat import (
    PrivateChatMiddleware,
    extract_chat,
    is_private_chat,
)

ADMIN_ID = 452536082
CUSTOMER_ID = 100200300
MANAGER_GROUP_ID = -1001234567890
RANDOM_GROUP_ID = -1009999999999

# Chat kinds the bot must ignore, with a representative id.
GROUPY = [
    ("group", RANDOM_GROUP_ID),
    ("supergroup", MANAGER_GROUP_ID),
    ("channel", -1005555555555),
]


def _chat(kind: str, chat_id: int) -> Chat:
    return Chat(id=chat_id, type=kind)


def _user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Tester")


def _message(chat: Chat, user: User, text: str = "/start") -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=text,
    )


def _update_message(chat: Chat, user: User, text: str = "/start") -> Update:
    return Update(update_id=1, message=_message(chat, user, text))


def _update_callback(chat: Chat, user: User, data: str = "catalog:open") -> Update:
    return Update(
        update_id=2,
        callback_query=CallbackQuery(
            id="cb-1",
            from_user=user,
            chat_instance="instance",
            data=data,
            message=_message(chat, user, "menu"),
        ),
    )


class Spy:
    """Stands in for the rest of the middleware chain."""

    def __init__(self) -> None:
        self.calls: list[TelegramObject] = []

    async def __call__(self, event: TelegramObject, data: dict[str, Any]) -> str:
        self.calls.append(event)
        return "handled"

    @property
    def called(self) -> bool:
        return bool(self.calls)


async def _run(update: Update) -> tuple[Any, Spy]:
    spy = Spy()
    result = await PrivateChatMiddleware()(spy, update, {})
    return result, spy


# ================================================== private chats pass


@pytest.mark.parametrize("user_id", [CUSTOMER_ID, ADMIN_ID])
@pytest.mark.parametrize("text", ["/start", "/admin", "🛍 Catalog", "any text"])
@pytest.mark.asyncio
async def test_private_chat_messages_are_processed(user_id: int, text: str) -> None:
    """A private chat is the same whether the sender is a customer or an admin."""
    chat = _chat("private", user_id)
    result, spy = await _run(_update_message(chat, _user(user_id), text))

    assert spy.called
    assert result == "handled"


@pytest.mark.parametrize("user_id", [CUSTOMER_ID, ADMIN_ID])
@pytest.mark.asyncio
async def test_private_callbacks_are_processed(user_id: int) -> None:
    chat = _chat("private", user_id)
    result, spy = await _run(_update_callback(chat, _user(user_id)))

    assert spy.called
    assert result == "handled"


# ================================================== group traffic dropped


@pytest.mark.parametrize("kind,chat_id", GROUPY)
@pytest.mark.parametrize(
    "text",
    ["/start", "/admin", "/orders", "/stats", "🛍 Catalog", "🛒 Cart", "hello"],
)
@pytest.mark.asyncio
async def test_group_messages_are_ignored(kind: str, chat_id: int, text: str) -> None:
    """Commands and menu-button text alike must be ignored in groups."""
    result, spy = await _run(_update_message(_chat(kind, chat_id), _user(ADMIN_ID), text))

    assert not spy.called, f"{text!r} was processed in a {kind}"
    assert result is None


@pytest.mark.parametrize("kind,chat_id", GROUPY)
@pytest.mark.parametrize(
    "data",
    [
        "catalog:open",
        "category:1",
        "subcat:1",
        "prod:1",
        "cart:add:1",
        "checkout:confirm",
        "checkout:pay:cash",
        "admin:ord:st:1:shipped:new:0",
        "admin:cat:del:1",
    ],
)
@pytest.mark.asyncio
async def test_group_callbacks_are_ignored(kind: str, chat_id: int, data: str) -> None:
    """Catalog, checkout and admin callbacks are all inert in a group."""
    result, spy = await _run(_update_callback(_chat(kind, chat_id), _user(ADMIN_ID), data))

    assert not spy.called, f"{data!r} was processed in a {kind}"
    assert result is None


@pytest.mark.asyncio
async def test_manager_group_is_notification_only() -> None:
    """An admin typing in the manager group gets no reply and no action."""
    manager = _chat("supergroup", MANAGER_GROUP_ID)
    for text in ("/start", "/admin", "/orders", "/stats"):
        result, spy = await _run(_update_message(manager, _user(ADMIN_ID), text))
        assert not spy.called
        assert result is None


@pytest.mark.asyncio
async def test_unrelated_group_is_equally_ignored() -> None:
    """A group the shop has nothing to do with is treated no differently."""
    random_group = _chat("group", RANDOM_GROUP_ID)
    result, spy = await _run(_update_message(random_group, _user(CUSTOMER_ID), "/start"))

    assert not spy.called
    assert result is None


@pytest.mark.asyncio
async def test_admin_privileges_do_not_bypass_the_gate() -> None:
    """Authorization is per-user; the chat rule is checked regardless."""
    for kind, chat_id in GROUPY:
        result, spy = await _run(_update_message(_chat(kind, chat_id), _user(ADMIN_ID), "/admin"))
        assert not spy.called, f"admin bypassed isolation in a {kind}"
        assert result is None


# ================================================== undeterminable origin


@pytest.mark.asyncio
async def test_callback_without_a_message_is_dropped() -> None:
    """Inline-mode callbacks carry no chat, so they cannot be judged private."""
    update = Update(
        update_id=3,
        callback_query=CallbackQuery(
            id="cb-2",
            from_user=_user(ADMIN_ID),
            chat_instance="instance",
            data="admin:cat:del:1",
            inline_message_id="inline-1",
        ),
    )
    result, spy = await _run(update)

    assert not spy.called
    assert result is None


@pytest.mark.asyncio
async def test_update_with_no_chat_is_dropped() -> None:
    result, spy = await _run(Update(update_id=4))

    assert not spy.called
    assert result is None


# ========================================================= helper units


@pytest.mark.parametrize("kind,chat_id", [("private", CUSTOMER_ID), *GROUPY])
def test_extract_chat_finds_the_origin(kind: str, chat_id: int) -> None:
    chat = _chat(kind, chat_id)
    assert extract_chat(_update_message(chat, _user(CUSTOMER_ID))) == chat
    assert extract_chat(_update_callback(chat, _user(CUSTOMER_ID))) == chat


def test_is_private_chat_only_accepts_private() -> None:
    assert is_private_chat(_chat("private", CUSTOMER_ID))
    assert not is_private_chat(None)
    for kind, chat_id in GROUPY:
        assert not is_private_chat(_chat(kind, chat_id))


# ===================================================== structural guarantee


def test_isolation_runs_before_the_database_session() -> None:
    """The ordering is the guarantee that a group update cannot touch state."""
    from aiogram import Dispatcher

    dispatcher = Dispatcher()
    setup_middlewares(dispatcher, None)  # type: ignore[arg-type]

    kinds = [type(mw) for mw in dispatcher.update.outer_middleware]
    assert PrivateChatMiddleware in kinds, "isolation middleware not registered"
    assert kinds.index(PrivateChatMiddleware) < kinds.index(DatabaseMiddleware), (
        "PrivateChatMiddleware must run before DatabaseMiddleware, otherwise a "
        "group update opens a database session before being dropped"
    )


@pytest.mark.asyncio
async def test_dropped_updates_reach_nothing_downstream() -> None:
    """No session, no FSM, no handler — the chain simply stops."""
    downstream_ran = False

    async def downstream(event: TelegramObject, data: dict[str, Any]) -> str:
        nonlocal downstream_ran
        downstream_ran = True
        return "should not happen"

    for kind, chat_id in GROUPY:
        result = await PrivateChatMiddleware()(
            downstream,
            _update_message(_chat(kind, chat_id), _user(ADMIN_ID), "/admin"),
            {},
        )
        assert result is None

    assert downstream_ran is False
