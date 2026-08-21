"""Admin category management keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.category import Category
from app.services.localization import LocalizationService
from app.utils.product_display import localized_category_name
from app.utils.telegram_ui import truncate_button_label

CALLBACK_CATEGORY_CREATE = "admin:cat:create"
CALLBACK_CATEGORY_LIST = "admin:cat:list"
CALLBACK_CATEGORY_VIEW_PREFIX = "admin:cat:view:"
CALLBACK_CATEGORY_RENAME_PREFIX = "admin:cat:ren:"
CALLBACK_CATEGORY_DELETE_PREFIX = "admin:cat:del:"
CALLBACK_CATEGORY_DELETE_OK_PREFIX = "admin:cat:delok:"
CALLBACK_CATEGORY_UP_PREFIX = "admin:cat:up:"
CALLBACK_CATEGORY_DOWN_PREFIX = "admin:cat:down:"
CALLBACK_CATEGORY_CANCEL = "admin:cat:cancel"
CALLBACK_CATEGORY_TOGGLE_PREFIX = "admin:cat:act:"  # admin:cat:act:{id}
CALLBACK_CATEGORY_EDIT_PREFIX = "admin:cat:edit:"  # language picker
CALLBACK_CATEGORY_NAME_PREFIX = "admin:cat:name:"  # admin:cat:name:{id}:{lang}

# Locale keys for the four supported languages, in display order.
LANGUAGE_KEYS: tuple[tuple[str, str], ...] = (
    ("ru", "language.ru"),
    ("en", "language.en"),
    ("de", "language.de"),
    ("uk", "language.uk"),
)


def _status_mark(i18n: LocalizationService, category: Category) -> str:
    return i18n.t(
        "admin.category_status_active" if category.is_active else "admin.category_status_inactive"
    )


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
                text=truncate_button_label(
                    f"{_status_mark(i18n, category)} "
                    f"{localized_category_name(category, i18n.language)}"
                ),
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
    subcategory_count: int = 0,
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
                text=i18n.t("admin.category_edit_names"),
                callback_data=f"{CALLBACK_CATEGORY_EDIT_PREFIX}{cid}",
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.t("admin.category_brands", count=subcategory_count),
                callback_data=f"admin:sub:list:{cid}",
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.t(
                    "admin.category_deactivate" if category.is_active else "admin.category_activate"
                ),
                callback_data=f"{CALLBACK_CATEGORY_TOGGLE_PREFIX}{cid}",
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


def category_language_keyboard(
    i18n: LocalizationService,
    category_id: int,
) -> InlineKeyboardMarkup:
    """Pick which localized category name to edit."""
    rows = [
        [
            InlineKeyboardButton(
                text=i18n.t(key),
                callback_data=f"{CALLBACK_CATEGORY_NAME_PREFIX}{category_id}:{code}",
            )
        ]
        for code, key in LANGUAGE_KEYS
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("common.back"),
                callback_data=f"{CALLBACK_CATEGORY_VIEW_PREFIX}{category_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
