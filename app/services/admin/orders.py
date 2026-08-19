"""Admin order operations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.models.order import Order
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.services.admin.exceptions import InvalidStatusTransitionError
from app.utils.order_status import allowed_transitions, can_transition


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
        """
        Move an order to ``status``, refusing transitions the lifecycle forbids.

        The keyboard only offers legal moves, but a stale message or a crafted
        callback could still ask for an illegal one, so the rule is enforced
        here rather than in the UI.
        """
        if order.status is status:
            return order
        if not can_transition(order.status, status):
            raise InvalidStatusTransitionError(order.status, status)
        return await self.orders.update_status(order, status)

    @staticmethod
    def allowed_next_statuses(order: Order) -> tuple[OrderStatus, ...]:
        """Statuses this order may move to, in lifecycle order."""
        return allowed_transitions(order.status)
