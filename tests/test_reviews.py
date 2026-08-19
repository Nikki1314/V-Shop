"""Reviews group access: invite links, failure handling, ID confidentiality."""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import Settings
from app.keyboards.info import (
    CALLBACK_INFO_REVIEWS,
    info_menu_keyboard,
    reviews_keyboard,
)
from app.services.localization import LocalizationService
from app.services.review import ReviewService, invalidate_review_link_cache

LANGS = ("ru", "en", "de", "uk")
GROUP_ID = -1001234567890
LINK = "https://t.me/+AbCdEf123456"


@pytest.fixture(autouse=True)
def _clear_link_cache() -> None:
    invalidate_review_link_cache()


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        bot_token="1:DUMMY",
        database_url="sqlite+aiosqlite://",
        manager_chat_id=-100999,
    )
    base.update(overrides)
    return Settings(**base)


class FakeInvite:
    def __init__(self, link: str) -> None:
        self.invite_link = link


class FakeBot:
    """Records Bot API calls so the service can be tested without Telegram."""

    def __init__(
        self,
        *,
        create: str | Exception | None = LINK,
        export: str | Exception | None = LINK,
    ) -> None:
        self._create = create
        self._export = export
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def create_chat_invite_link(self, **kwargs: Any) -> FakeInvite:
        self.calls.append(("create_chat_invite_link", kwargs))
        if isinstance(self._create, Exception):
            raise self._create
        if self._create is None:
            return FakeInvite("")
        return FakeInvite(self._create)

    async def export_chat_invite_link(self, **kwargs: Any) -> str:
        self.calls.append(("export_chat_invite_link", kwargs))
        if isinstance(self._export, Exception):
            raise self._export
        if self._export is None:
            raise TelegramForbiddenError(method=None, message="no rights")  # type: ignore[arg-type]
        return self._export


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=None, message=message)  # type: ignore[arg-type]


# ------------------------------------------------------------ configuration


def test_reviews_disabled_without_configuration() -> None:
    settings = _settings()
    assert settings.review_group_chat_id is None
    assert settings.reviews_enabled is False


def test_reviews_enabled_by_group_or_static_link() -> None:
    assert _settings(review_group_chat_id=GROUP_ID).reviews_enabled is True
    assert _settings(review_invite_link=LINK).reviews_enabled is True


@pytest.mark.asyncio
async def test_disabled_service_returns_no_link() -> None:
    bot = FakeBot()
    service = ReviewService(bot, _settings())  # type: ignore[arg-type]

    assert service.is_enabled is False
    assert await service.get_invite_link() is None
    assert bot.calls == [], "must not call Telegram when unconfigured"


# ------------------------------------------------------------- link sources


@pytest.mark.asyncio
async def test_static_link_is_used_without_calling_telegram() -> None:
    bot = FakeBot()
    service = ReviewService(bot, _settings(review_invite_link=LINK))  # type: ignore[arg-type]

    assert await service.get_invite_link() == LINK
    assert bot.calls == []


@pytest.mark.asyncio
async def test_link_is_created_through_the_bot_api() -> None:
    bot = FakeBot()
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]

    assert await service.get_invite_link() == LINK
    assert bot.calls[0][0] == "create_chat_invite_link"
    assert bot.calls[0][1]["chat_id"] == GROUP_ID
    assert bot.calls[0][1]["name"]


@pytest.mark.asyncio
async def test_falls_back_to_export_when_create_is_refused() -> None:
    """Bots that may invite but not manage links still work."""
    bot = FakeBot(create=_bad_request("not enough rights to manage invite links"))
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]

    assert await service.get_invite_link() == LINK
    assert [name for name, _ in bot.calls] == [
        "create_chat_invite_link",
        "export_chat_invite_link",
    ]


@pytest.mark.asyncio
async def test_link_is_cached_between_presses() -> None:
    bot = FakeBot()
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]

    for _ in range(5):
        assert await service.get_invite_link() == LINK
    assert len(bot.calls) == 1, "one API call should serve repeated presses"

    invalidate_review_link_cache()
    assert await service.get_invite_link() == LINK
    assert len(bot.calls) == 2


# ------------------------------------------------------ graceful failure


@pytest.mark.asyncio
async def test_both_api_calls_failing_returns_none() -> None:
    bot = FakeBot(
        create=_bad_request("CHAT_ADMIN_REQUIRED"),
        export=_bad_request("CHAT_ADMIN_REQUIRED"),
    )
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]

    assert await service.get_invite_link() is None


@pytest.mark.asyncio
async def test_bot_removed_from_the_group_returns_none() -> None:
    forbidden = TelegramForbiddenError(method=None, message="bot was kicked")  # type: ignore[arg-type]
    bot = FakeBot(create=forbidden, export=forbidden)
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]

    assert await service.get_invite_link() is None


@pytest.mark.asyncio
async def test_unexpected_error_is_swallowed() -> None:
    bot = FakeBot(create=RuntimeError("boom"), export=RuntimeError("boom"))
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]

    assert await service.get_invite_link() is None


@pytest.mark.asyncio
async def test_failure_is_not_cached() -> None:
    """A transient outage must not disable the button for an hour."""
    bot = FakeBot(
        create=_bad_request("temporary"), export=_bad_request("temporary")
    )
    service = ReviewService(bot, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]
    assert await service.get_invite_link() is None

    working = FakeBot()
    recovered = ReviewService(working, _settings(review_group_chat_id=GROUP_ID))  # type: ignore[arg-type]
    assert await recovered.get_invite_link() == LINK


# ------------------------------------------------------- ID confidentiality


@pytest.mark.parametrize("language", LANGS)
def test_customer_message_never_exposes_the_group_id(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    text = i18n.t("info.reviews_text")
    markup = reviews_keyboard(i18n, LINK)

    rendered = [text] + [
        f"{b.text}{b.url or ''}{b.callback_data or ''}"
        for row in markup.inline_keyboard
        for b in row
    ]
    for chunk in rendered:
        assert str(GROUP_ID) not in chunk
        assert str(abs(GROUP_ID)) not in chunk
        assert "1234567890" not in chunk


def test_link_is_delivered_as_a_url_button() -> None:
    markup = reviews_keyboard(LocalizationService.from_code("en"), LINK)
    buttons = [b for row in markup.inline_keyboard for b in row]

    assert buttons[0].url == LINK
    assert buttons[0].callback_data is None
    assert buttons[-1].callback_data == "info:open"  # a way back


# ------------------------------------------------------------ localization


@pytest.mark.parametrize("language", LANGS)
def test_reviews_button_present_in_information_menu(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    entries = [
        (b.text, b.callback_data)
        for row in info_menu_keyboard(i18n).inline_keyboard
        for b in row
    ]
    payloads = [data for _, data in entries]
    labels = [text for text, _ in entries]

    assert CALLBACK_INFO_REVIEWS in payloads
    assert len(payloads) == 6, "Information must offer all six entries"
    reviews_label = labels[payloads.index(CALLBACK_INFO_REVIEWS)]
    assert reviews_label == i18n.t("info.btn_reviews")
    assert reviews_label.startswith("⭐")


def test_review_strings_are_translated_not_copied() -> None:
    keys = ("info.btn_reviews", "info.reviews_text", "info.reviews_open",
            "info.reviews_unavailable")
    for key in keys:
        rendered = {
            LocalizationService.from_code(code).t(key) for code in LANGS
        }
        assert len(rendered) == len(LANGS), f"{key} is not translated per language"
        for value in rendered:
            assert value and not value.startswith("info."), key
