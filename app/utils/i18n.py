"""Low-level locale loading utilities.

Add a new language by creating ``app/locales/<code>.json`` and registering
the code in ``SUPPORTED_LANGUAGES`` / ``LanguageCode``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.enums import LanguageCode

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(code.value for code in LanguageCode)
DEFAULT_LANGUAGE = LanguageCode.EN.value


def flatten_locale(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested locale JSON into dotted keys (``menu.catalog``)."""
    flat: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_locale(value, full_key))
        else:
            flat[full_key] = str(value)
    return flat


@lru_cache(maxsize=16)
def load_locale(language: str) -> dict[str, str]:
    """Load and flatten a locale JSON file."""
    code = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    path = LOCALES_DIR / f"{code}.json"
    if not path.exists():
        if code == DEFAULT_LANGUAGE:
            raise FileNotFoundError(f"Default locale file missing: {path}")
        return load_locale(DEFAULT_LANGUAGE)

    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Locale file must contain a JSON object: {path}")
    return flatten_locale(data)


def normalize_language(language: LanguageCode | str | None) -> str:
    """Normalize a language code to a supported locale string."""
    if language is None:
        return DEFAULT_LANGUAGE
    code = language.value if isinstance(language, LanguageCode) else str(language).lower()
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def translate(
    key: str,
    language: LanguageCode | str | None = None,
    **kwargs: object,
) -> str:
    """Translate ``key`` for ``language`` with optional ``str.format`` kwargs."""
    code = normalize_language(language)
    catalog = load_locale(code)
    template = catalog.get(key)
    if template is None and code != DEFAULT_LANGUAGE:
        template = load_locale(DEFAULT_LANGUAGE).get(key)
    if template is None:
        return key

    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def translations_for(key: str) -> frozenset[str]:
    """Return every supported-language translation of ``key``."""
    values = {translate(key, language) for language in SUPPORTED_LANGUAGES}
    values.discard(key)
    return frozenset(values)


@lru_cache(maxsize=128)
def translations_for_cached(key: str) -> frozenset[str]:
    return translations_for(key)


def clear_locale_cache() -> None:
    """Clear cached locale catalogs (useful in tests)."""
    load_locale.cache_clear()
    translations_for_cached.cache_clear()


def locale_keys(language: LanguageCode | str | None = None) -> set[str]:
    return set(load_locale(normalize_language(language)).keys())


def assert_locales_in_sync() -> None:
    """Raise if locale files do not share the same key set."""
    base_keys = locale_keys(DEFAULT_LANGUAGE)
    for code in SUPPORTED_LANGUAGES:
        keys = locale_keys(code)
        missing = base_keys - keys
        extra = keys - base_keys
        if missing or extra:
            raise ValueError(
                f"Locale {code!r} is out of sync with {DEFAULT_LANGUAGE!r}. "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )
