"""Admin user / broadcast recipient queries."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository


class AdminUserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def list_broadcast_recipient_ids(self) -> list[int]:
        return await self.users.list_telegram_ids()

    async def count_users(self) -> int:
        return await self.users.count()
