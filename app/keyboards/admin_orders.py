"""Admin order management keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.enums import OrderStatus
from app.models.order import Order
from app.services.localization import LocalizationService
from app.utils.order_status import status_code, status_from_code, status_label
from app.utils.telegram_ui import truncate_button_label

CALLBACK_ORDER_ACTIONS = "admin:ord:actions"
CALLBACK_ORDER_NEW = "admin:ord:new"
CALLBACK_ORDER_NEW_PREFIX = "admin:ord:new:"
CALLBACK_ORDER_DONE = "admin:ord:done"
CALLBACK_ORDER_DONE_PREFIX = "admin:ord:done:"
CALLBACK_ORDER_SEARCH = "admin:ord:search"
CALLBACK_ORDER_VIEW_PREFIX = "admin:ord:view:"
CALLBACK_ORDER_STATUS_PREFIX = "admin:ord:st:"  # admin:ord:st:{id}:{code}
CALLBACK_ORDER_CANCEL = "admin:ord:cancel"

ORDERS_PAGE_SIZE = 8

# Re-exported for existing handler imports.
__all__ = (
    "CALLBACK_ORDER_ACTIONS",
    "CALLBACK_ORDER_NEW",
    "CALLBACK_ORDER_NEW_PREFIX",
    "CALLBACK_ORDER_DONE",
    "CALLBACK_ORDER_DONE_PREFIX",
    "CALLBACK_ORDER_SEARCH",
    "CALLBACK_ORDER_VIEW_PREFIX",
    "CALLBACK_ORDER_STATUS_PREFIX",
    "CALLBACK_ORDER_CANCEL",
    "ORDERS_PAGE_SIZE",
    "status_label",
    "status_code",
    "status_from_code",
)


def orders_actions_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.orders_view_new"),
                    callback_data=CALLBACK_ORDER_NEW,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.orders_view_completed"),
                    callback_data=CALLBACK_ORDER_DONE,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.orders_search"),
                    callback_data=CALLBACK_ORDER_SEARCH,
                )
            ],
        ]
    )


def _order_list_label(order: Order, i18n: LocalizationService) -> str:
    status = status_label(i18n, order.status)
    label = f"#{order.id} · {status} · {order.customer_name} · {order.total_price}"
    return truncate_button_label(label)


def orders_list_keyboard(
    i18n: LocalizationService,
    orders: list[Order],
    *,
    page: int,
    total: int,
    list_kind: str,
) -> InlineKeyboardMarkup:
    """list_kind is ``new`` or ``done``."""
    prefix = CALLBACK_ORDER_NEW_PREFIX if list_kind == "new" else CALLBACK_ORDER_DONE_PREFIX
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_order_list_label(order, i18n),
                callback_data=f"{CALLBACK_ORDER_VIEW_PREFIX}{order.id}:{list_kind}:{page}",
            )
        ]
        for order in orders
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text=i18n.t("admin.orders_prev"),
                callback_data=f"{prefix}{page - 1}",
            )
        )
    max_page = max(0, (total - 1) // ORDERS_PAGE_SIZE) if total else 0
    if page < max_page:
        nav.append(
            InlineKeyboardButton(
                text=i18n.t("admin.orders_next"),
                callback_data=f"{prefix}{page + 1}",
            )
        )
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("common.back"),
                callback_data=CALLBACK_ORDER_ACTIONS,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_keyboard(
    i18n: LocalizationService,
    orders: list[Order],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_order_list_label(order, i18n),
                callback_data=f"{CALLBACK_ORDER_VIEW_PREFIX}{order.id}:search:0",
            )
        ]
        for order in orders
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("common.back"),
                callback_data=CALLBACK_ORDER_ACTIONS,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_manage_keyboard(
    i18n: LocalizationService,
    order: Order,
    *,
    list_kind: str = "new",
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    status_row: list[InlineKeyboardButton] = []
    for status in OrderStatus:
        if status == order.status:
            continue
        status_row.append(
            InlineKeyboardButton(
                text=status_label(i18n, status),
                callback_data=(
                    f"{CALLBACK_ORDER_STATUS_PREFIX}{order.id}:{status_code(status)}"
                    f":{list_kind}:{page}"
                ),
            )
        )
        if len(status_row) == 2:
            rows.append(status_row)
            status_row = []
    if status_row:
        rows.append(status_row)

    if list_kind == "done":
        back_data = f"{CALLBACK_ORDER_DONE_PREFIX}{page}"
    elif list_kind == "search":
        back_data = CALLBACK_ORDER_ACTIONS
    else:
        back_data = f"{CALLBACK_ORDER_NEW_PREFIX}{page}"

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.orders_back_list"),
                callback_data=back_data,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
