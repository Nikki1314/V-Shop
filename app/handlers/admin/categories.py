"""Admin categories: create, rename, delete, reorder."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters.localized_text import LocalizedText
from app.keyboards.admin import admin_cancel_keyboard, admin_menu_keyboard
from app.keyboards.admin_categories import (
    CALLBACK_CATEGORY_CANCEL,
    CALLBACK_CATEGORY_CREATE,
    CALLBACK_CATEGORY_DELETE_OK_PREFIX,
    CALLBACK_CATEGORY_DELETE_PREFIX,
    CALLBACK_CATEGORY_DOWN_PREFIX,
    CALLBACK_CATEGORY_LIST,
    CALLBACK_CATEGORY_RENAME_PREFIX,
    CALLBACK_CATEGORY_UP_PREFIX,
    CALLBACK_CATEGORY_VIEW_PREFIX,
    categories_actions_keyboard,
    categories_admin_list_keyboard,
    category_delete_confirm_keyboard,
    category_manage_keyboard,
)
from app.models.category import Category
from app.services.admin import AdminService, CategoryInUseError
from app.services.localization import LocalizationService
from app.states.admin import (
    ADMIN_WIZARD_STATES,
    CreateCategoryStates,
    RenameCategoryStates,
)
from app.utils.telegram_ui import edit_or_answer
from app.utils.validators import nonempty, parse_callback_id

logger = logging.getLogger(__name__)

router = Router(name="admin_categories")


async def _cancel_category_wizard(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(
        i18n.t("admin.category_cancelled"),
        reply_markup=admin_menu_keyboard(i18n),
    )


async def _show_categories_list(
    message: Message,
    i18n: LocalizationService,
    session: AsyncSession,
    *,
    edit: bool = False,
) -> None:
    categories = await AdminService(session).list_categories()
    if not categories:
        text = i18n.t("admin.category_list_empty")
        markup = categories_actions_keyboard(i18n)
    else:
        text = i18n.t("admin.category_list_title", total=len(categories))
        markup = categories_admin_list_keyboard(i18n, categories)

    await edit_or_answer(message, text, reply_markup=markup, edit=edit)


def _category_index(categories: list[Category], category_id: int) -> int | None:
    for index, category in enumerate(categories):
        if category.id == category_id:
            return index
    return None


async def _send_category_view(
    message: Message,
    i18n: LocalizationService,
    session: AsyncSession,
    category: Category,
    *,
    edit: bool = False,
) -> None:
    admin = AdminService(session)
    categories = await admin.list_categories()
    index = _category_index(categories, category.id)
    if index is None:
        await message.answer(i18n.t("admin.category_not_found"))
        return

    product_count = await admin.count_category_products(category.id)
    text = i18n.t(
        "admin.category_card",
        category_id=category.id,
        name=category.name,
        position=index + 1,
        total=len(categories),
        products=product_count,
    )
    markup = category_manage_keyboard(
        i18n,
        category,
        index=index,
        total=len(categories),
    )
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            logger.debug("Could not edit category view", exc_info=True)
    await message.answer(text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Section entry
# ---------------------------------------------------------------------------


@router.message(LocalizedText("admin.menu_categories"), ~StateFilter(*ADMIN_WIZARD_STATES))
async def open_categories(message: Message, i18n: LocalizationService) -> None:
    await message.answer(
        i18n.t("admin.section_categories"),
        reply_markup=admin_menu_keyboard(i18n),
    )
    await message.answer(
        i18n.t("admin.category_actions"),
        reply_markup=categories_actions_keyboard(i18n),
    )


@router.callback_query(F.data == CALLBACK_CATEGORY_LIST)
async def show_categories_list(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await _show_categories_list(callback.message, i18n, session, edit=True)


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_VIEW_PREFIX))
async def view_category(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_callback_id(callback.data, CALLBACK_CATEGORY_VIEW_PREFIX)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    await callback.answer()
    await state.clear()

    category = await AdminService(session).get_category(category_id)
    if category is None:
        await callback.message.answer(i18n.t("admin.category_not_found"))
        return

    await _send_category_view(callback.message, i18n, session, category, edit=True)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.callback_query(F.data == CALLBACK_CATEGORY_CREATE)
async def start_create_category(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(CreateCategoryStates.name)
    await callback.message.answer(
        i18n.t("admin.category_ask_name"),
        reply_markup=admin_cancel_keyboard(i18n),
    )


@router.message(StateFilter(CreateCategoryStates.name), LocalizedText("common.cancel"))
@router.message(StateFilter(RenameCategoryStates.name), LocalizedText("common.cancel"))
async def cancel_category_wizard_message(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await _cancel_category_wizard(message, i18n, state)


@router.callback_query(
    StateFilter(CreateCategoryStates, RenameCategoryStates),
    F.data == CALLBACK_CATEGORY_CANCEL,
)
async def cancel_category_wizard_callback(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _cancel_category_wizard(callback.message, i18n, state)


@router.message(StateFilter(CreateCategoryStates.name), F.text)
async def process_create_category(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    name = nonempty(message.text, min_len=1, max_len=255)
    if name is None:
        await message.answer(
            i18n.t("admin.category_name_invalid"),
            reply_markup=admin_cancel_keyboard(i18n),
        )
        return

    admin = AdminService(session)
    existing = await admin.get_category_by_name(name)
    if existing is not None:
        await message.answer(
            i18n.t("admin.category_name_exists"),
            reply_markup=admin_cancel_keyboard(i18n),
        )
        return

    category = await admin.create_category(name)
    await state.clear()
    await message.answer(
        i18n.t("admin.category_created", name=category.name, category_id=category.id),
        reply_markup=admin_menu_keyboard(i18n),
    )
    await _send_category_view(message, i18n, session, category)


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_RENAME_PREFIX))
async def start_rename_category(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_callback_id(callback.data, CALLBACK_CATEGORY_RENAME_PREFIX)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    await callback.answer()
    category = await AdminService(session).get_category(category_id)
    if category is None:
        await callback.message.answer(i18n.t("admin.category_not_found"))
        return

    await state.set_state(RenameCategoryStates.name)
    await state.update_data(category_id=category.id, current_name=category.name)
    await callback.message.answer(
        i18n.t("admin.category_ask_rename", current=category.name),
        reply_markup=admin_cancel_keyboard(i18n),
    )


@router.message(StateFilter(RenameCategoryStates.name), F.text)
async def process_rename_category(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    name = nonempty(message.text, min_len=1, max_len=255)
    if name is None:
        await message.answer(
            i18n.t("admin.category_name_invalid"),
            reply_markup=admin_cancel_keyboard(i18n),
        )
        return

    data = await state.get_data()
    admin = AdminService(session)
    category = await admin.get_category(int(data["category_id"]))
    if category is None:
        await state.clear()
        await message.answer(
            i18n.t("admin.category_not_found"),
            reply_markup=admin_menu_keyboard(i18n),
        )
        return

    existing = await admin.get_category_by_name(name)
    if existing is not None and existing.id != category.id:
        await message.answer(
            i18n.t("admin.category_name_exists"),
            reply_markup=admin_cancel_keyboard(i18n),
        )
        return

    category = await admin.rename_category(category, name)
    await state.clear()
    await message.answer(
        i18n.t("admin.category_renamed", name=category.name),
        reply_markup=admin_menu_keyboard(i18n),
    )
    await _send_category_view(message, i18n, session, category)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_DELETE_PREFIX))
async def ask_delete_category(
    callback: CallbackQuery,
    i18n: LocalizationService,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_callback_id(callback.data, CALLBACK_CATEGORY_DELETE_PREFIX)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        i18n.t("admin.category_delete_ask", category_id=category_id),
        reply_markup=category_delete_confirm_keyboard(i18n, category_id),
    )


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_DELETE_OK_PREFIX))
async def confirm_delete_category(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_callback_id(callback.data, CALLBACK_CATEGORY_DELETE_OK_PREFIX)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    await callback.answer()
    admin = AdminService(session)
    category = await admin.get_category(category_id)
    if category is None:
        await callback.message.answer(i18n.t("admin.category_not_found"))
        return

    name = category.name
    try:
        await admin.delete_category(category)
    except CategoryInUseError:
        await callback.message.answer(i18n.t("admin.category_delete_in_use"))
        category = await admin.get_category(category_id)
        if category is not None:
            await _send_category_view(callback.message, i18n, session, category)
        return

    await state.clear()
    await callback.message.answer(
        i18n.t("admin.category_deleted", name=name, category_id=category_id),
        reply_markup=admin_menu_keyboard(i18n),
    )
    await _show_categories_list(callback.message, i18n, session)


# ---------------------------------------------------------------------------
# Change order
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_UP_PREFIX))
async def move_category_up(
    callback: CallbackQuery,
    i18n: LocalizationService,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_callback_id(callback.data, CALLBACK_CATEGORY_UP_PREFIX)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return
    await AdminService(session).move_category(category_id, direction=-1)
    category = await AdminService(session).get_category(category_id)
    if category is None:
        await callback.answer(i18n.t("admin.category_not_found"), show_alert=True)
        return
    await callback.answer(i18n.t("admin.category_order_updated"))
    await _send_category_view(callback.message, i18n, session, category, edit=True)


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_DOWN_PREFIX))
async def move_category_down(
    callback: CallbackQuery,
    i18n: LocalizationService,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_callback_id(callback.data, CALLBACK_CATEGORY_DOWN_PREFIX)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return
    await AdminService(session).move_category(category_id, direction=+1)
    category = await AdminService(session).get_category(category_id)
    if category is None:
        await callback.answer(i18n.t("admin.category_not_found"), show_alert=True)
        return
    await callback.answer(i18n.t("admin.category_order_updated"))
    await _send_category_view(callback.message, i18n, session, category, edit=True)


@router.message(StateFilter(CreateCategoryStates.name))
async def process_create_category_invalid(
    message: Message,
    i18n: LocalizationService,
) -> None:
    await message.answer(
        i18n.t("admin.category_name_invalid"),
        reply_markup=admin_cancel_keyboard(i18n),
    )


@router.message(StateFilter(RenameCategoryStates.name))
async def process_rename_category_invalid(
    message: Message,
    i18n: LocalizationService,
) -> None:
    await message.answer(
        i18n.t("admin.category_name_invalid"),
        reply_markup=admin_cancel_keyboard(i18n),
    )
