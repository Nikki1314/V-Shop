"""Admin category management keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.category import Category
from app.services.localization import LocalizationService

CALLBACK_CATEGORY_CREATE = "admin:cat:create"
CALLBACK_CATEGORY_LIST = "admin:cat:list"
CALLBACK_CATEGORY_VIEW_PREFIX = "admin:cat:view:"
CALLBACK_CATEGORY_RENAME_PREFIX = "admin:cat:ren:"
CALLBACK_CATEGORY_DELETE_PREFIX = "admin:cat:del:"
CALLBACK_CATEGORY_DELETE_OK_PREFIX = "admin:cat:delok:"
CALLBACK_CATEGORY_UP_PREFIX = "admin:cat:up:"
CALLBACK_CATEGORY_DOWN_PREFIX = "admin:cat:down:"
CALLBACK_CATEGORY_CANCEL = "admin:cat:cancel"


def categories_actions_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.category_create"),
                    callback_data=CALLBACK_CATEGORY_CREATE,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.category_manage_list"),
                    callback_data=CALLBACK_CATEGORY_LIST,
                )
            ],
        ]
    )


def categories_admin_list_keyboard(
    i18n: LocalizationService,
    categories: list[Category],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"#{index + 1} {category.name}",
                callback_data=f"{CALLBACK_CATEGORY_VIEW_PREFIX}{category.id}",
            )
        ]
        for index, category in enumerate(categories)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.category_create"),
                callback_data=CALLBACK_CATEGORY_CREATE,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_manage_keyboard(
    i18n: LocalizationService,
    category: Category,
    *,
    index: int,
    total: int,
) -> InlineKeyboardMarkup:
    cid = category.id
    move_row: list[InlineKeyboardButton] = []
    if index > 0:
        move_row.append(
            InlineKeyboardButton(
                text=i18n.t("admin.category_move_up"),
                callback_data=f"{CALLBACK_CATEGORY_UP_PREFIX}{cid}",
            )
        )
    if index < total - 1:
        move_row.append(
            InlineKeyboardButton(
                text=i18n.t("admin.category_move_down"),
                callback_data=f"{CALLBACK_CATEGORY_DOWN_PREFIX}{cid}",
            )
        )

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.t("admin.category_rename"),
                callback_data=f"{CALLBACK_CATEGORY_RENAME_PREFIX}{cid}",
            )
        ],
    ]
    if move_row:
        rows.append(move_row)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.category_delete"),
                    callback_data=f"{CALLBACK_CATEGORY_DELETE_PREFIX}{cid}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.category_back_list"),
                    callback_data=CALLBACK_CATEGORY_LIST,
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_delete_confirm_keyboard(
    i18n: LocalizationService,
    category_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.category_delete_confirm"),
                    callback_data=f"{CALLBACK_CATEGORY_DELETE_OK_PREFIX}{category_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("common.cancel"),
                    callback_data=f"{CALLBACK_CATEGORY_VIEW_PREFIX}{category_id}",
                )
            ],
        ]
    )
