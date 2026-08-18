"""Admin subcategory (brand) management keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.category import Category, Subcategory
from app.services.localization import LocalizationService
from app.utils.telegram_ui import truncate_button_label

# Namespaced short callbacks — Telegram caps callback data at 64 bytes.
CALLBACK_SUB_LIST_PREFIX = "admin:sub:list:"  # admin:sub:list:{category_id}
CALLBACK_SUB_VIEW_PREFIX = "admin:sub:view:"  # admin:sub:view:{subcategory_id}
CALLBACK_SUB_CREATE_PREFIX = "admin:sub:new:"  # admin:sub:new:{category_id}
CALLBACK_SUB_EDIT_PREFIX = "admin:sub:edit:"  # admin:sub:edit:{subcategory_id}
CALLBACK_SUB_NAME_PREFIX = "admin:sub:name:"  # admin:sub:name:{id}:{lang}
CALLBACK_SUB_TOGGLE_PREFIX = "admin:sub:act:"  # admin:sub:act:{subcategory_id}
CALLBACK_SUB_UP_PREFIX = "admin:sub:up:"
CALLBACK_SUB_DOWN_PREFIX = "admin:sub:down:"
CALLBACK_SUB_DELETE_PREFIX = "admin:sub:del:"
CALLBACK_SUB_DELETE_OK_PREFIX = "admin:sub:delok:"
CALLBACK_SUB_ASSIGN_PREFIX = "admin:sub:asg:"  # pick destination category
CALLBACK_SUB_ASSIGN_TO_PREFIX = "admin:sub:asgto:"  # admin:sub:asgto:{id}:{cat}
CALLBACK_SUB_CANCEL = "admin:sub:cancel"

# Locale keys for the four supported languages, in display order.
LANGUAGE_KEYS: tuple[tuple[str, str], ...] = (
    ("ru", "language.ru"),
    ("en", "language.en"),
    ("de", "language.de"),
    ("uk", "language.uk"),
)


def _label(subcategory: Subcategory, i18n: LocalizationService) -> str:
    status = (
        i18n.t("admin.subcategory_status_active")
        if subcategory.is_active
        else i18n.t("admin.subcategory_status_inactive")
    )
    return truncate_button_label(f"{status} {subcategory.name_ru}")


def subcategories_list_keyboard(
    i18n: LocalizationService,
    category_id: int,
    subcategories: list[Subcategory],
) -> InlineKeyboardMarkup:
    """One row per brand, plus create and back."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_label(sub, i18n),
                callback_data=f"{CALLBACK_SUB_VIEW_PREFIX}{sub.id}",
            )
        ]
        for sub in subcategories
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_create"),
                callback_data=f"{CALLBACK_SUB_CREATE_PREFIX}{category_id}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.category_back_list"),
                callback_data=f"admin:cat:view:{category_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_manage_keyboard(
    i18n: LocalizationService,
    subcategory: Subcategory,
    *,
    index: int,
    total: int,
) -> InlineKeyboardMarkup:
    sid = subcategory.id
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_edit_names"),
                callback_data=f"{CALLBACK_SUB_EDIT_PREFIX}{sid}",
            )
        ]
    ]

    toggle_key = (
        "admin.subcategory_deactivate"
        if subcategory.is_active
        else "admin.subcategory_activate"
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t(toggle_key),
                callback_data=f"{CALLBACK_SUB_TOGGLE_PREFIX}{sid}",
            )
        ]
    )

    move_row: list[InlineKeyboardButton] = []
    if index > 0:
        move_row.append(
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_move_up"),
                callback_data=f"{CALLBACK_SUB_UP_PREFIX}{sid}",
            )
        )
    if index < total - 1:
        move_row.append(
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_move_down"),
                callback_data=f"{CALLBACK_SUB_DOWN_PREFIX}{sid}",
            )
        )
    if move_row:
        rows.append(move_row)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_assign"),
                callback_data=f"{CALLBACK_SUB_ASSIGN_PREFIX}{sid}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_delete"),
                callback_data=f"{CALLBACK_SUB_DELETE_PREFIX}{sid}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("admin.subcategory_back_list"),
                callback_data=f"{CALLBACK_SUB_LIST_PREFIX}{subcategory.category_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_language_keyboard(
    i18n: LocalizationService,
    subcategory_id: int,
) -> InlineKeyboardMarkup:
    """Pick which localized name to edit."""
    rows = [
        [
            InlineKeyboardButton(
                text=i18n.t(key),
                callback_data=f"{CALLBACK_SUB_NAME_PREFIX}{subcategory_id}:{code}",
            )
        ]
        for code, key in LANGUAGE_KEYS
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("common.back"),
                callback_data=f"{CALLBACK_SUB_VIEW_PREFIX}{subcategory_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_assign_keyboard(
    i18n: LocalizationService,
    subcategory: Subcategory,
    categories: list[Category],
) -> InlineKeyboardMarkup:
    """Choose a destination category (the current one is omitted)."""
    rows = [
        [
            InlineKeyboardButton(
                text=truncate_button_label(category.name_ru),
                callback_data=(
                    f"{CALLBACK_SUB_ASSIGN_TO_PREFIX}{subcategory.id}:{category.id}"
                ),
            )
        ]
        for category in categories
        if category.id != subcategory.category_id
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.t("common.back"),
                callback_data=f"{CALLBACK_SUB_VIEW_PREFIX}{subcategory.id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_delete_confirm_keyboard(
    i18n: LocalizationService,
    subcategory_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("admin.subcategory_delete_confirm"),
                    callback_data=f"{CALLBACK_SUB_DELETE_OK_PREFIX}{subcategory_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("common.cancel"),
                    callback_data=f"{CALLBACK_SUB_VIEW_PREFIX}{subcategory_id}",
                )
            ],
        ]
    )
