"""Generic async repository base class with shared CRUD operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT: Base]:
    """Encapsulates common persistence operations for a single ORM model."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Create -----------------------------------------------------------------

    def create(self, **kwargs: Any) -> ModelT:
        """Instantiate a model instance without persisting it."""
        return self.model(**kwargs)

    async def add(self, entity: ModelT) -> ModelT:
        """Persist a new entity and flush to obtain generated fields."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_all(self, entities: Sequence[ModelT]) -> list[ModelT]:
        """Persist multiple entities in one flush."""
        self.session.add_all(entities)
        await self.session.flush()
        return list(entities)

    async def create_and_add(self, **kwargs: Any) -> ModelT:
        """Instantiate and immediately persist an entity."""
        return await self.add(self.create(**kwargs))

    # --- Read -------------------------------------------------------------------

    async def get_by_id(self, entity_id: int) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ModelT]:
        stmt = select(self.model).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def exists(self, entity_id: int) -> bool:
        result = await self.session.scalars(
            select(self.model.id).where(self.model.id == entity_id).limit(1)  # type: ignore[attr-defined]
        )
        return result.first() is not None

    async def count(self) -> int:
        result = await self.session.scalar(select(func.count()).select_from(self.model))
        return int(result or 0)

    # --- Update -----------------------------------------------------------------

    async def update(self, entity: ModelT, **fields: Any) -> ModelT:
        """Apply field updates to an entity and flush."""
        for key, value in fields.items():
            if not hasattr(entity, key):
                raise AttributeError(f"{self.model.__name__} has no attribute {key!r}")
            setattr(entity, key, value)
        await self.session.flush()
        return entity

    # --- Delete -----------------------------------------------------------------

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_by_id(self, entity_id: int) -> bool:
        """Delete by primary key. Returns True if a row was deleted."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        await self.delete(entity)
        return True

    # --- Session helpers --------------------------------------------------------

    async def refresh(self, entity: ModelT, attribute_names: Sequence[str] | None = None) -> ModelT:
        await self.session.refresh(entity, attribute_names=attribute_names)
        return entity

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
