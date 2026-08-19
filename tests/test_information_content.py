"""Information section content: payment wording, contacts placeholder, menu."""

from __future__ import annotations

import json
import pathlib

import pytest

from app.keyboards.info import (
    CALLBACK_INFO_CHANGE_CITY,
    CALLBACK_INFO_CHANGE_LANGUAGE,
    CALLBACK_INFO_CONTACTS,
    CALLBACK_INFO_DELIVERY,
    CALLBACK_INFO_OPEN,
    CALLBACK_INFO_PAYMENT,
    CALLBACK_INFO_REVIEWS,
    info_back_keyboard,
    info_menu_keyboard,
)
from app.services.localization import LocalizationService

LANGS = ("ru", "en", "de", "uk")
PAYMENT_KEYS = ("info.berlin.payment", "info.other.payment")
CONTACT_KEYS = ("info.berlin.contacts", "info.other.contacts")
LOCALES = pathlib.Path(__file__).resolve().parent.parent / "app" / "locales"

# "by request" as written in each language
BY_REQUEST = {
    "en": "by request",
    "ru": "по запросу",
    "de": "auf Anfrage",
    "uk": "за запитом",
}
UNDER_DEVELOPMENT = {
    "en": "Under development",
    "ru": "В разработке",
    "de": "In Entwicklung",
    "uk": "У розробці",
}
REVIEWS_HINT = {
    "en": "Reviews group",
    "ru": "группе отзывов",
    "de": "Bewertungsgruppe",
    "uk": "групі відгуків",
}


def _buttons(markup):  # type: ignore[no-untyped-def]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


# ------------------------------------------------------------------ payment


def test_paypal_is_gone_from_every_locale_file() -> None:
    """Scans the raw files, so a stray mention anywhere is caught."""
    for code in LANGS:
        raw = (LOCALES / f"{code}.json").read_text(encoding="utf-8")
        assert "paypal" not in raw.lower(), f"PayPal still present in {code}.json"


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.parametrize("key", PAYMENT_KEYS)
def test_payment_offers_transfer_by_request(language: str, key: str) -> None:
    text = LocalizationService.from_code(language).t(key)

    assert BY_REQUEST[language] in text, f"{key} ({language}) must say 'by request'"
    assert "paypal" not in text.lower()


@pytest.mark.parametrize("language", LANGS)
def test_cash_stays_where_it_applies(language: str) -> None:
    """Cash is offered for Berlin pickup/courier, not for postal delivery."""
    i18n = LocalizationService.from_code(language)
    cash = {"en": "Cash", "ru": "Наличные", "de": "Barzahlung", "uk": "Готівка"}

    assert cash[language] in i18n.t("info.berlin.payment")
    assert cash[language] not in i18n.t("info.other.payment")


@pytest.mark.parametrize("key", PAYMENT_KEYS)
def test_payment_text_is_translated_per_language(key: str) -> None:
    rendered = {LocalizationService.from_code(c).t(key) for c in LANGS}
    assert len(rendered) == len(LANGS)


# ----------------------------------------------------------------- contacts


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.parametrize("key", CONTACT_KEYS)
def test_contacts_is_the_placeholder(language: str, key: str) -> None:
    text = LocalizationService.from_code(language).t(key)

    assert UNDER_DEVELOPMENT[language] in text
    assert REVIEWS_HINT[language] in text, "must point customers at the Reviews group"


@pytest.mark.parametrize("language", LANGS)
def test_old_contact_details_are_gone(language: str) -> None:
    """The placeholder replaces the previous handles, phone and hours."""
    for key in CONTACT_KEYS:
        text = LocalizationService.from_code(language).t(key)
        for stale in ("@vshop_support", "+49 000", "support@v-shop.example", "12:00"):
            assert stale not in text, f"{key} ({language}) still shows {stale!r}"


@pytest.mark.parametrize("key", CONTACT_KEYS)
def test_contacts_text_is_translated_per_language(key: str) -> None:
    rendered = {LocalizationService.from_code(c).t(key) for c in LANGS}
    assert len(rendered) == len(LANGS)


@pytest.mark.parametrize("language", LANGS)
def test_contacts_screen_offers_reviews_and_back(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    entries = _buttons(info_back_keyboard(i18n, with_reviews=True))

    assert entries[0] == (i18n.t("info.btn_reviews"), CALLBACK_INFO_REVIEWS)
    assert entries[-1] == (i18n.t("info.back"), CALLBACK_INFO_OPEN)


@pytest.mark.parametrize("language", LANGS)
def test_other_topics_keep_a_plain_back_button(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    entries = _buttons(info_back_keyboard(i18n))

    assert entries == [(i18n.t("info.back"), CALLBACK_INFO_OPEN)]


# --------------------------------------------------------------------- menu


@pytest.mark.parametrize("language", LANGS)
def test_information_menu_keeps_every_entry(language: str) -> None:
    i18n = LocalizationService.from_code(language)
    payloads = [data for _, data in _buttons(info_menu_keyboard(i18n))]

    assert payloads == [
        CALLBACK_INFO_DELIVERY,
        CALLBACK_INFO_PAYMENT,
        CALLBACK_INFO_CONTACTS,
        CALLBACK_INFO_REVIEWS,
        CALLBACK_INFO_CHANGE_LANGUAGE,
        CALLBACK_INFO_CHANGE_CITY,
    ]


@pytest.mark.parametrize("language", LANGS)
def test_delivery_text_untouched(language: str) -> None:
    """Delivery was not in scope; it must still be real content."""
    i18n = LocalizationService.from_code(language)
    for key in ("info.berlin.delivery", "info.other.delivery"):
        text = i18n.t(key)
        assert len(text) > 80
        assert UNDER_DEVELOPMENT[language] not in text


def test_locale_catalogs_stay_in_sync() -> None:
    base = set(json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))["info"])
    for code in LANGS:
        info = json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))["info"]
        assert set(info) == base, f"{code}.json info section drifted"
