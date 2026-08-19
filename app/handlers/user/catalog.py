"""Customer catalog: Category → Subcategory → Product → Card, with Back.

Navigation is one message that gets edited in place as the customer drills down,
so the chat does not fill with dead menus. The product card is sent as its own
message because a photo card cannot replace a text message; its Back button
returns to the product list.

Nothing inactive is ever shown: every read goes through
:class:`~app.services.catalog.CatalogService`, whose queries join upwards, so a
live product inside a hidden brand stays hidden.
"""

from __future__ import annotations

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
    CALLBACK_PRODUCT_PREFIX,
    CALLBACK_SUBCATEGORY_PREFIX,
    categories_keyboard,
    category_view_keyboard,
    products_keyboard,
    subcategories_keyboard,
    subcategory_view_keyboard,
)
from app.keyboards.product import add_to_cart_keyboard
from app.models.product import Product
from app.services.catalog import CatalogService
from app.services.localization import LocalizationService
from app.utils.html import e
from app.utils.product_display import format_product_card, localized_category_name
from app.utils.validators import parse_positive_int

logger = logging.getLogger(__name__)

router = Router(name="user_catalog")


def _message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    return message if isinstance(message, Message) else None


async def _render(
    message: Message,
    text: str,
    markup: object,
    *,
    edit: bool,
) -> None:
    """Edit the current screen in place, falling back to a new message.

    The fallback matters when the previous screen was a photo product card:
    Telegram cannot turn a photo message into a text one.
    """
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]
            return
        except TelegramBadRequest:
            logger.debug("Could not edit catalog screen; sending a new one")
    await message.answer(text, reply_markup=markup)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Level 1 — categories
# ---------------------------------------------------------------------------


async def _show_categories(
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
            await _render(message, text, None, edit=True)
        else:
            await answer_with_menu(message, text, i18n)
        return

    await _render(
        message,
        i18n.t("catalog.choose_category"),
        categories_keyboard(categories, i18n.language),
        edit=edit,
    )


@router.message(LocalizedText("menu.catalog"))
async def open_catalog(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Reply-keyboard entry point."""
    await state.clear()
    ready = await ensure_onboarded_user(message, session, state)
    if ready is None:
        return
    _user, i18n = ready
    await _show_categories(session=session, i18n=i18n, message=message)


@router.callback_query(F.data == CALLBACK_CATALOG_OPEN)
async def back_to_categories(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    """Back from brands, and 'continue shopping' from the cart."""
    message = _message(callback)
    if message is None:
        await callback.answer()
        return
    await callback.answer()
    await _show_categories(session=session, i18n=i18n, message=message, edit=True)


# ---------------------------------------------------------------------------
# Level 2 — subcategories / brands
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_PREFIX))
async def open_category(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    """A category was chosen — show its brands."""
    message = _message(callback)
    if message is None or callback.data is None:
        await callback.answer()
        return

    category_id = parse_positive_int(
        callback.data.removeprefix(CALLBACK_CATEGORY_PREFIX)
    )
    if category_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    catalog = CatalogService(session)
    category, subcategories = await catalog.get_category_with_subcategories(category_id)
    if category is None:
        await callback.answer(i18n.t("catalog.not_found"), show_alert=True)
        return

    await callback.answer()
    header = i18n.t(
        "catalog.category_opened",
        name=e(localized_category_name(category, i18n.language)),
    )
    if not subcategories:
        await _render(
            message,
            f"{header}\n\n{i18n.t('catalog.no_subcategories')}",
            category_view_keyboard(i18n),
            edit=True,
        )
        return

    await _render(
        message,
        f"{header}\n\n{i18n.t('catalog.choose_subcategory')}",
        subcategories_keyboard(i18n, subcategories),
        edit=True,
    )


# ---------------------------------------------------------------------------
# Level 3 — products
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(CALLBACK_SUBCATEGORY_PREFIX))
async def open_subcategory(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    """A brand was chosen — show its products. Also Back from a product card."""
    message = _message(callback)
    if message is None or callback.data is None:
        await callback.answer()
        return

    subcategory_id = parse_positive_int(
        callback.data.removeprefix(CALLBACK_SUBCATEGORY_PREFIX)
    )
    if subcategory_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    catalog = CatalogService(session)
    subcategory, products = await catalog.get_subcategory_with_products(subcategory_id)
    if subcategory is None:
        await callback.answer(i18n.t("catalog.subcategory_not_found"), show_alert=True)
        return

    category = await catalog.get_category(subcategory.category_id)
    await callback.answer()
    header = i18n.t(
        "catalog.subcategory_opened",
        category=e(
            localized_category_name(category, i18n.language) if category else ""
        ),
        name=e(localized_category_name(subcategory, i18n.language)),
    )
    if not products:
        await _render(
            message,
            f"{header}\n\n{i18n.t('catalog.subcategory_empty')}",
            subcategory_view_keyboard(i18n, subcategory.category_id),
            edit=True,
        )
        return

    await _render(
        message,
        f"{header}\n\n{i18n.t('catalog.choose_product')}",
        products_keyboard(i18n, products, category_id=subcategory.category_id),
        edit=True,
    )


# ---------------------------------------------------------------------------
# Level 4 — product card
# ---------------------------------------------------------------------------


async def _send_product_card(
    message: Message,
    product: Product,
    i18n: LocalizationService,
) -> None:
    caption = format_product_card(product, i18n)
    markup = add_to_cart_keyboard(
        i18n, product.id, subcategory_id=product.subcategory_id
    )

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


@router.callback_query(F.data.startswith(CALLBACK_PRODUCT_PREFIX))
async def open_product(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    """A product was chosen — show its card."""
    message = _message(callback)
    if message is None or callback.data is None:
        await callback.answer()
        return

    product_id = parse_positive_int(callback.data.removeprefix(CALLBACK_PRODUCT_PREFIX))
    if product_id is None:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    product = await CatalogService(session).get_product(product_id)
    if product is None:
        await callback.answer(i18n.t("product.not_found"), show_alert=True)
        return

    await callback.answer()
    await _send_product_card(message, product, i18n)
