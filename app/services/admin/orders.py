"""Admin order operations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.models.order import Order
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository


class AdminOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.order_items = OrderItemRepository(session)

    async def list_orders_by_status(
        self,
        status: OrderStatus,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Order]:
        return await self.orders.list_by_status(status, offset=offset, limit=limit)

    async def count_orders_by_status(self, status: OrderStatus) -> int:
        return await self.orders.count_by_status(status)

    async def page_orders_by_status(
        self,
        status: OrderStatus,
        *,
        offset: int = 0,
        limit: int,
    ) -> tuple[int, list[Order]]:
        total = await self.count_orders_by_status(status)
        items = await self.list_orders_by_status(status, offset=offset, limit=limit)
        return total, items

    async def get_order(self, order_id: int) -> Order | None:
        return await self.orders.get_with_items(order_id)

    async def search_orders(self, query: str, *, limit: int = 20) -> list[Order]:
        return await self.orders.search(query, limit=limit)

    async def set_order_status(self, order: Order, status: OrderStatus) -> Order:
        return await self.orders.update_status(order, status)
