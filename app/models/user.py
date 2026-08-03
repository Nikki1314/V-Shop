"""User model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import CityChoice, LanguageCode
from app.models.types import enum_values

if TYPE_CHECKING:
    from app.models.cart import Cart
    from app.models.order import Order


class User(Base, TimestampMixin):
    """Registered Telegram shop user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[LanguageCode | None] = mapped_column(
        Enum(
            LanguageCode,
            name="language_code",
            native_enum=False,
            length=8,
            values_callable=enum_values,
        ),
        nullable=True,
    )
    selected_city: Mapped[CityChoice | None] = mapped_column(
        Enum(
            CityChoice,
            name="city_choice",
            native_enum=False,
            length=32,
            values_callable=enum_values,
        ),
        nullable=True,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    cart: Mapped[Cart | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    orders: Mapped[list[Order]] = relationship(
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id}>"
