"""Shared pytest fixtures — in-memory async SQLite for repository/service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.base import Base
from app.models.category import Category
from app.models.enums import CityChoice, LanguageCode
from app.models.product import Product
from app.models.user import User

# Import models so metadata is complete.
import app.models  # noqa: F401


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    entity = User(
        telegram_id=1001,
        username="buyer",
        first_name="Buyer",
        language=LanguageCode.EN,
        selected_city=CityChoice.BERLIN,
    )
    session.add(entity)
    await session.flush()
    return entity


@pytest_asyncio.fixture
async def category(session: AsyncSession) -> Category:
    entity = Category(name="Liquids", sort_order=0)
    session.add(entity)
    await session.flush()
    return entity


@pytest_asyncio.fixture
async def product(session: AsyncSession, category: Category) -> Product:
    entity = Product(
        category_id=category.id,
        name_ru="Тест",
        name_en="Test Juice",
        name_de="Test Saft",
        description_ru="Описание",
        description_en="Description",
        description_de="Beschreibung",
        flavor="Mango",
        volume="30ml",
        nicotine_strength="3mg",
        price=Decimal("12.50"),
        is_active=True,
    )
    session.add(entity)
    await session.flush()
    return entity
