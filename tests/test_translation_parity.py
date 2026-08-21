"""
No unintended fallback language.

``test_locales_are_in_sync`` proves the four catalogs have the same *keys*. This
proves they have genuinely different *values* — a key copied from English into
ru/de/uk passes the key check while showing an English string to a Russian
customer, which is the failure mode that matters to a user.

Every legitimate exception is listed with its reason, and the list is checked
both ways: an untranslated string that is not listed fails, and a listed key
that has since been translated fails too, so the list cannot rot.
"""

from __future__ import annotations

import re

import pytest

from app.utils.i18n import SUPPORTED_LANGUAGES, load_locale

PLACEHOLDER = re.compile(r"\{(\w+)\}")
TAG = re.compile(r"</?[a-zA-Z]+>")

# Keys whose value is deliberately identical to English, and why. Anything not
# in here must actually be translated.
INTENTIONALLY_IDENTICAL: dict[str, str] = {
    # A language picker shows every language in its own name — that is the point
    # of an endonym. "Deutsch" stays "Deutsch" for a Russian speaker.
    "language.ru": "endonym",
    "language.en": "endonym",
    "language.de": "endonym",
    "language.uk": "endonym",
    # Product name, not a word to translate.
    "checkout.phone_via_telegram": "brand name",
}

# Per-language exceptions: words that happen to be spelled the same.
INTENTIONALLY_IDENTICAL_PER_LANGUAGE: dict[str, dict[str, str]] = {
    "de": {
        "admin.broadcast_kind_text": "'Text' is the German word too",
        "checkout.summary_name": "'Name' is the German word too",
        "city.berlin": "Berlin is spelled the same in German",
    },
}


def literal_body(template: str) -> str:
    """Template text with placeholders and markup removed."""
    return "".join(ch for ch in TAG.sub("", PLACEHOLDER.sub("", template)) if ch.isalnum())


def is_prose(value: str) -> bool:
    """
    True when a value carries real words, rather than layout.

    ``"{icon} {label}: <b>{value}</b>"`` is a layout template and is identical in
    every catalog on purpose; it is not a translation gap.
    """
    return sum(ch.isalpha() for ch in literal_body(value)) >= 4


def allowed(language: str, key: str) -> bool:
    if key in INTENTIONALLY_IDENTICAL:
        return True
    return key in INTENTIONALLY_IDENTICAL_PER_LANGUAGE.get(language, {})


@pytest.mark.parametrize("language", [c for c in SUPPORTED_LANGUAGES if c != "en"])
def test_no_key_silently_falls_back_to_english(language: str) -> None:
    english = load_locale("en")
    catalog = load_locale(language)

    untranslated = sorted(
        key
        for key, value in catalog.items()
        if english.get(key) == value and is_prose(value) and not allowed(language, key)
    )

    assert untranslated == [], (
        f"{language}: {len(untranslated)} string(s) still show English to a "
        f"{language} speaker: {untranslated}. Translate them, or add the key to "
        "INTENTIONALLY_IDENTICAL with a reason."
    )


@pytest.mark.parametrize("language", [c for c in SUPPORTED_LANGUAGES if c != "en"])
def test_the_exception_list_does_not_rot(language: str) -> None:
    """A listed key that has since been translated must leave the list."""
    english = load_locale("en")
    catalog = load_locale(language)

    stale = sorted(
        key
        for key in {
            **INTENTIONALLY_IDENTICAL,
            **INTENTIONALLY_IDENTICAL_PER_LANGUAGE.get(language, {}),
        }
        if key in catalog and english.get(key) != catalog[key]
    )

    assert stale == [], (
        f"{language}: these keys are listed as intentionally identical to English "
        f"but now differ — remove them from the list: {stale}"
    )


def test_every_exception_key_exists() -> None:
    english = load_locale("en")
    missing = sorted(
        key
        for key in {
            *INTENTIONALLY_IDENTICAL,
            *(k for per in INTENTIONALLY_IDENTICAL_PER_LANGUAGE.values() for k in per),
        }
        if key not in english
    )
    assert missing == [], f"exception list names keys that do not exist: {missing}"


@pytest.mark.parametrize("language", [c for c in SUPPORTED_LANGUAGES if c != "en"])
def test_placeholders_match_english_in_every_language(language: str) -> None:
    """
    A dropped or invented ``{placeholder}`` raises at render time, in production.

    Compared as multisets, so a translation may legitimately reorder them —
    ``€{amount}`` becoming ``{amount} €`` — but never add or lose one.
    """
    from collections import Counter

    english = load_locale("en")
    catalog = load_locale(language)

    mismatched = {
        key: (sorted(PLACEHOLDER.findall(english[key])), sorted(PLACEHOLDER.findall(value)))
        for key, value in catalog.items()
        if key in english
        and Counter(PLACEHOLDER.findall(english[key])) != Counter(PLACEHOLDER.findall(value))
    }

    assert mismatched == {}, f"{language}: placeholder mismatch: {mismatched}"


# A separator IS whitespace — ru/uk group thousands with U+202F — so these keys
# are exempt from the "not blank" rule rather than being special-cased inside it.
WHITESPACE_VALUED = {"format.group_separator", "format.decimal_separator"}


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_no_locale_value_is_empty(language: str) -> None:
    catalog = load_locale(language)
    empty = sorted(
        key
        for key, value in catalog.items()
        if not value or (not value.strip() and key not in WHITESPACE_VALUED)
    )
    assert empty == [], f"{language}: empty translations: {empty}"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_html_tags_are_balanced(language: str) -> None:
    """
    Telegram rejects a message whose HTML does not parse.

    An unbalanced tag introduced by a translator fails the send at runtime, for
    that language only — exactly the kind of bug that reaches production.
    """
    catalog = load_locale(language)
    broken = {}
    for key, value in catalog.items():
        opened: list[str] = []
        for match in re.finditer(r"<(/?)([a-zA-Z]+)>", value):
            closing, tag = match.group(1), match.group(2)
            if not closing:
                opened.append(tag)
            elif not opened or opened.pop() != tag:
                broken[key] = value
                break
        else:
            if opened:
                broken[key] = value
    assert broken == {}, f"{language}: unbalanced HTML: {broken}"


# Values that are legitimately Latin in a Cyrillic catalog.
LATIN_IN_CYRILLIC_OK = {"checkout.phone_via_telegram"}


@pytest.mark.parametrize("language", ["ru", "uk"])
def test_no_cyrillic_string_is_written_in_latin(language: str) -> None:
    """
    Per key, not per catalog.

    A catalog-wide ratio cannot see a whole section flip to English — the share
    barely moves — so each string is judged on its own. Markup and placeholders
    are stripped first, since the letters in ``<b>`` and ``{name}`` are not
    prose, and brand names are listed explicitly.
    """
    catalog = load_locale(language)
    latin: dict[str, str] = {}

    for key, value in catalog.items():
        if key.startswith(("format.", "language.")) or key in LATIN_IN_CYRILLIC_OK:
            continue
        letters = [ch for ch in TAG.sub("", PLACEHOLDER.sub("", value)) if ch.isalpha()]
        if len(letters) < 4:
            continue
        cyrillic = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
        if cyrillic * 2 <= len(letters):
            latin[key] = value[:60]

    assert latin == {}, (
        f"{language}: these strings are mostly Latin script — they read as "
        f"English to a {language} speaker: {latin}"
    )
