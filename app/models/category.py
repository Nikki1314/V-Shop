"""Category model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Category(Base):
    """Product category (brand, flavor group, strength, etc.)."""

    __tablename__ = "categories"
    __table_args__ = (
        Index("ix_categories_sort_order", "sort_order"),
        Index("ix_categories_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )


    products: Mapped[list[Product]] = relationship(
        back_populates="category",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"
