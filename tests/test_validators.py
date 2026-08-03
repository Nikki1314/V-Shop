"""Validators unit tests (shared input parsing)."""

from __future__ import annotations

from decimal import Decimal

from app.utils.validators import (
    allowlist,
    nonempty,
    normalize_phone,
    parse_callback_id,
    parse_nonnegative_int,
    parse_positive_int,
    parse_price,
)


def test_parse_price_valid_and_invalid() -> None:
    assert parse_price("12.50") == Decimal("12.50")
    assert parse_price("12,5") == Decimal("12.50")
    assert parse_price("0") is None
    assert parse_price("1e3") is None
    assert parse_price("abc") is None


def test_normalize_phone() -> None:
    assert normalize_phone("+49 123 456789") == "+49123456789"
    assert normalize_phone("123") is None
    assert normalize_phone(None) is None


def test_parse_ints_and_callback() -> None:
    assert parse_positive_int("12") == 12
    assert parse_positive_int("0") is None
    assert parse_nonnegative_int("0") == 0
    assert parse_callback_id("admin:product:view:9", "admin:product:view:") == 9
    assert parse_callback_id("bad", "admin:product:view:") is None


def test_nonempty_and_allowlist() -> None:
    assert nonempty("  hi  ") == "hi"
    assert nonempty("   ") is None
    assert allowlist("new", frozenset({"new", "done"})) == "new"
    assert allowlist("x", frozenset({"new"})) is None
