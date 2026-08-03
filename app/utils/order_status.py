"""Order status codecs and labels (UI-agnostic)."""

from __future__ import annotations

from app.models.enums import OrderStatus
from app.services.localization import LocalizationService

_STATUS_LOCALE = {
    OrderStatus.NEW: "admin.order_status_new",
    OrderStatus.ACCEPTED: "admin.order_status_accepted",
    OrderStatus.COMPLETED: "admin.order_status_completed",
    OrderStatus.CANCELLED: "admin.order_status_cancelled",
}


def status_label(i18n: LocalizationService, status: OrderStatus | str) -> str:
    if isinstance(status, str):
        try:
            status = OrderStatus(status)
        except ValueError:
            return status
    key = _STATUS_LOCALE.get(status)
    return i18n.t(key) if key else str(status)


def status_code(status: OrderStatus) -> str:
    return status.name.lower()


def status_from_code(code: str) -> OrderStatus | None:
    try:
        return OrderStatus[code.upper()]
    except KeyError:
        return None
