"""Category browsing and product cards via Inline Keyboards."""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters.localized_text import LocalizedText
from app.handlers.user.navigation import answer_with_menu, ensure_onboarded_user
from app.keyboards.catalog import (
    CALLBACK_CATALOG_OPEN,
    CALLBACK_CATEGORY_PREFIX,
    categories_keyboard,
    category_view_keyboard,
)
from app.keyboards.product import add_to_cart_keyboard
from app.models.product import Product
from app.services.catalog import CatalogService
from app.services.localization import LocalizationService
from app.utils.html import e
from app.utils.product_display import format_product_card
from app.utils.validators import parse_positive_int

logger = logging.getLogger(__name__)

router = Router(name="user_catalog")

# Small delay between product cards to reduce Telegram flood-control risk.
_PRODUCT_CARD_PACING_SECONDS = 0.05


async def _render_category_list(
    *,
    session: AsyncSession,
    i18n: LocalizationService,
    message: Message,
    edit: bool = False,
) -> None:
    categories = await CatalogService(session).list_categories()
    if not categories:
        text = i18n.t("catalog.empty")
        if edit:
            await message.edit_text(text)
        else:
            await answer_with_menu(message, text, i18n)
        return

    await session.commit()

    text = i18n.t("catalog.choose_category")
    markup = categories_keyboard(categories)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_product_card(
    message: Message,
    product: Product,
    i18n: LocalizationService,
) -> None:
    caption = format_product_card(product, i18n)
    markup = add_to_cart_keyboard(i18n, product.id)

    if product.image_file_id:
        try:
            await message.answer_photo(
                photo=product.image_file_id,
                caption=caption,
                reply_markup=markup,
            )
            return
        except TelegramBadRequest:
            logger.warning(
                "Invalid product image_file_id=%s product_id=%s; sending text card",
                product.image_file_id,
                product.id,
            )

    await message.answer(caption, reply_markup=markup)


async def _render_category_with_products(
    *,
    session: AsyncSession,
    i18n: LocalizationService,
    message: Message,
    category_id: int,
    edit_header: bool = False,
) -> None:
    catalog = CatalogService(session)
    category, products = await catalog.get_category_with_products(category_id)
    if category is None:
        text = i18n.t("catalog.not_found")
        if edit_header:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    header = i18n.t("catalog.category_opened", name=e(category.name))
    header_markup = category_view_keyboard(i18n)

    # Release the DB transaction before sequential Telegram I/O.
    await session.commit()

    if not products:
        text = f"{header}\n\n{i18n.t('catalog.category_empty')}"
        if edit_header:
            await message.edit_text(text, reply_markup=header_markup)
        else:
            await message.answer(text, reply_markup=header_markup)
        return

    if edit_header:
        await message.edit_text(header, reply_markup=header_markup)
    else:
        await message.answer(header, reply_markup=header_markup)

    for index, product in enumerate(products):
        if index:
            await asyncio.sleep(_PRODUCT_CARD_PACING_SECONDS)
        await _send_product_card(message, product, i18n)


@router.message(LocalizedText("menu.catalog"))
async def open_catalog(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Reply Keyboard → show category list as Inline Keyboard."""
    await state.clear()
    ready = await ensure_onboarded_user(message, session, state)
    if ready is None:
        return
    _user, i18n = ready
    await _render_category_list(session=session, i18n=i18n, message=message, edit=False)


@router.callback_query(F.data == CALLBACK_CATALOG_OPEN)
async def catalog_open_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    """Inline: return to / refresh the category list."""
    if callback.message is None:
        await callback.answer()
        return

    await callback.answer()
    try:
        await _render_category_list(
            session=session,
            i18n=i18n,
            message=callback.message,
            edit=True,
        )
    except TelegramBadRequest:
        await _render_category_list(
            session=session,
            i18n=i18n,
            message=callback.message,
            edit=False,
        )


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_PREFIX))
async def open_category(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    """Inline: open category and send product cards."""
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    raw_id = callback.data.removeprefix(CALLBACK_CATEGORY_PREFIX)
    category_id = parse_positive_int(raw_id)
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    await callback.answer()
    try:
        await _render_category_with_products(
            session=session,
            i18n=i18n,
            message=callback.message,
            category_id=category_id,
            edit_header=True,
        )
    except TelegramBadRequest:
        await _render_category_with_products(
            session=session,
            i18n=i18n,
            message=callback.message,
            category_id=category_id,
            edit_header=False,
        )
