"""Startup database-identity probe (read-only diagnostic)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import DatabaseIdentity, read_database_identity
from tests.factories import make_category, make_product


@pytest.mark.asyncio
async def test_identity_reports_counts_for_known_tables(session: AsyncSession) -> None:
    category = await make_category(session, name="Liquids")
    await make_product(session, category)
    await session.flush()

    identity = await read_database_identity(session)

    assert identity.counts["categories"] == 1
    assert identity.counts["products"] == 1
    assert identity.counts["users"] == 0
    assert identity.counts["orders"] == 0


@pytest.mark.asyncio
async def test_identity_probe_is_read_only(session: AsyncSession) -> None:
    """The probe must not create, modify or delete anything."""
    before = await read_database_identity(session)
    await read_database_identity(session)
    after = await read_database_identity(session)

    assert before.counts == after.counts


@pytest.mark.asyncio
async def test_identity_degrades_when_backend_lacks_pg_control(
    session: AsyncSession,
) -> None:
    """SQLite has no pg_control_system(); the probe returns None, never raises."""
    identity = await read_database_identity(session)

    assert identity.system_identifier is None
    assert identity.counts["categories"] is not None


@pytest.mark.asyncio
async def test_empty_catalog_is_flagged(session: AsyncSession) -> None:
    empty = await read_database_identity(session)
    assert empty.catalog_is_empty is True

    category = await make_category(session, name="Liquids")
    await make_product(session, category)
    await session.flush()

    populated = await read_database_identity(session)
    assert populated.catalog_is_empty is False


def test_identity_defaults_are_inert() -> None:
    assert DatabaseIdentity().catalog_is_empty is True
