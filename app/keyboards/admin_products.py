"""Admin products / Add Product wizard keyboards."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.models.category import Category, Subcategory
from app.models.product import Product
from app.services.localization import LocalizationService
from app.utils.product_display import localized_product_name
from app.utils.telegram_ui import truncate_button_label

CALLBACK_PRODUCT_ADD = "admin:product:add"
CALLBACK_PRODUCT_ACTIONS = "admin:product:actions"
CALLBACK_PRODUCT_LIST = "admin:product:list"
CALLBACK_PRODUCT_LIST_PREFIX = "admin:product:list:"
CALLBACK_PRODUCT_VIEW_PREFIX = "admin:product:view:"
CALLBACK_PRODUCT_EDIT_PREFIX = "admin:product:edit:"
CALLBACK_PRODUCT_PRICE_PREFIX = "admin:product:price:"
CALLBACK_PRODUCT_DESC_PREFIX = "admin:product:desc:"
CALLBACK_PRODUCT_ENABLE_PREFIX = "admin:product:en:"
CALLBACK_PRODUCT_DISABLE_PREFIX = "admin:product:dis:"
CALLBACK_PRODUCT_DELETE_PREFIX = "admin:product:del:"
CALLBACK_PRODUCT_DELETE_OK_PREFIX = "admin:product:delok:"
CALLBACK_PRODUCT_CAT_PREFIX = "admin:product:cat:"
CALLBACK_PRODUCT_EDIT_CAT_PREFIX = "admin:product:ecat:"
CALLBACK_PRODUCT_SUB_PREFIX = "admin:product:sub:"
CALLBACK_PRODUCT_EDIT_SUB_PREFIX = "admin:product:esub:"
CALLBACK_PRODUCT_CONFIRM = "admin:product:confirm"
CALLBACK_PRODUCT_EDIT_CONFIRM = "admin:product:econfirm"
CALLBACK_PRODUCT_CANCEL = "admin:product:cancel"

PRODUCTS_PAGE_SIZE = 8


def products_actions_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.products_add"),
                    callback_data=CALLBACK_PRODUCT_ADD,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.products_manage"),
                    callback_data=CALLBACK_PRODUCT_LIST,
                )
            ],
        ]
    )


def admin_category_pick_keyboard(
    categories: list[Category],
    *,
    prefix: str = CALLBACK_PRODUCT_CAT_PREFIX,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category.name,
                    callback_data=f"{prefix}{category.id}",
                )
            ]
            for category in categories
        ]
    )


def admin_product_confirm_keyboard(
    i18n: LocalizationService,
    *,
    confirm_callback: str = CALLBACK_PRODUCT_CONFIRM,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("common.confirm"),
                    callback_data=confirm_callback,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("common.cancel"),
                    callback_data=CALLBACK_PRODUCT_CANCEL,
                )
            ],
        ]
    )


def _product_list_label(product: Product, i18n: LocalizationService) -> str:
    status = "✅" if product.is_active else "⛔"
    name = localized_product_name(product, i18n.language)
    label = f"{status} #{product.id} {name}"
    return truncate_button_label(label)


def products_list_keyboard(
    i18n: LocalizationService,
    products: list[Product],
    *,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_product_list_label(product, i18n),
                callback_data=f"{CALLBACK_PRODUCT_VIEW_PREFIX}{product.id}",
            )
        ]
        for product in products
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text=i18n.t("admin.products_prev"),
                callback_data=f"{CALLBACK_PRODUCT_LIST_PREFIX}{page - 1}",
            )
        )
    max_page = max(0, (total - 1) // PRODUCTS_PAGE_SIZE)
    if page < max_page:
        nav.append(
            InlineKeyboardButton(
                text=i18n.t("admin.products_next"),
                callback_data=f"{CALLBACK_PRODUCT_LIST_PREFIX}{page + 1}",
            )
        )
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("common.back"),
                callback_data=CALLBACK_PRODUCT_ACTIONS,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_manage_keyboard(
    i18n: LocalizationService,
    product: Product,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    pid = product.id
    toggle_row = (
        [
            InlineKeyboardButton(
                text=i18n.t("admin.product_disable"),
                callback_data=f"{CALLBACK_PRODUCT_DISABLE_PREFIX}{pid}",
            )
        ]
        if product.is_active
        else [
            InlineKeyboardButton(
                text=i18n.t("admin.product_enable"),
                callback_data=f"{CALLBACK_PRODUCT_ENABLE_PREFIX}{pid}",
            )
        ]
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.product_edit"),
                    callback_data=f"{CALLBACK_PRODUCT_EDIT_PREFIX}{pid}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.product_edit_price"),
                    callback_data=f"{CALLBACK_PRODUCT_PRICE_PREFIX}{pid}",
                ),
                InlineKeyboardButton(
                    text=i18n.t("admin.product_edit_description"),
                    callback_data=f"{CALLBACK_PRODUCT_DESC_PREFIX}{pid}",
                ),
            ],
            toggle_row,
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.product_delete"),
                    callback_data=f"{CALLBACK_PRODUCT_DELETE_PREFIX}{pid}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.products_back_list"),
                    callback_data=f"{CALLBACK_PRODUCT_LIST_PREFIX}{page}",
                )
            ],
        ]
    )


def product_delete_confirm_keyboard(
    i18n: LocalizationService,
    product_id: int,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.product_delete_confirm"),
                    callback_data=f"{CALLBACK_PRODUCT_DELETE_OK_PREFIX}{product_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("common.cancel"),
                    callback_data=f"{CALLBACK_PRODUCT_VIEW_PREFIX}{product_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.products_back_list"),
                    callback_data=f"{CALLBACK_PRODUCT_LIST_PREFIX}{page}",
                )
            ],
        ]
    )


def admin_subcategory_pick_keyboard(
    subcategories: list[Subcategory],
    *,
    prefix: str = CALLBACK_PRODUCT_SUB_PREFIX,
) -> InlineKeyboardMarkup:
    """Brand picker; only brands of the already-chosen category are passed in."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=truncate_button_label(sub.name_ru),
                    callback_data=f"{prefix}{sub.id}",
                )
            ]
            for sub in subcategories
        ]
    )
