"""Category and Subcategory models (catalog hierarchy)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from app.models.product import Product


class Category(Base, TimestampMixin, UpdatedAtMixin):
    """
    Top level of the catalog: Category → Subcategory → Product.

    ``name`` is the pre-hierarchy single-language column. It is retained (and
    kept in sync on write) so the current admin/catalog handlers keep working
    while the localized columns are adopted. A later contract migration drops
    it — see docs/database-schema.md.
    """

    __tablename__ = "categories"
    __table_args__ = (
        Index("ix_categories_sort_order", "sort_order"),
        Index("ix_categories_name", "name"),
        Index("ix_categories_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Legacy single-language name (deprecated; superseded by name_*).
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_de: Mapped[str] = mapped_column(String(255), nullable=False)
    name_uk: Mapped[str] = mapped_column(String(255), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    subcategories: Mapped[list[Subcategory]] = relationship(
        back_populates="category",
        order_by="Subcategory.sort_order",
    )
    # Legacy direct link, retained alongside products.category_id.
    products: Mapped[list[Product]] = relationship(
        back_populates="category",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name_en={self.name_en!r}>"


class Subcategory(Base, TimestampMixin, UpdatedAtMixin):
    """Second level of the catalog — a brand or product group within a category."""

    __tablename__ = "subcategories"
    __table_args__ = (
        Index("ix_subcategories_category_id_is_active", "category_id", "is_active"),
        Index("ix_subcategories_sort_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_de: Mapped[str] = mapped_column(String(255), nullable=False)
    name_uk: Mapped[str] = mapped_column(String(255), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    category: Mapped[Category] = relationship(back_populates="subcategories")
    products: Mapped[list[Product]] = relationship(back_populates="subcategory")

    def __repr__(self) -> str:
        return (
            f"<Subcategory id={self.id} category_id={self.category_id} "
            f"name_en={self.name_en!r}>"
        )
