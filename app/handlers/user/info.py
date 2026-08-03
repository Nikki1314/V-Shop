"""Information page — city-dependent content + language/city change."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters.localized_text import LocalizedText
from app.handlers.user.navigation import ensure_onboarded_user
from app.keyboards.info import (
    CALLBACK_INFO_CHANGE_CITY,
    CALLBACK_INFO_CHANGE_LANGUAGE,
    CALLBACK_INFO_CONTACTS,
    CALLBACK_INFO_DELIVERY,
    CALLBACK_INFO_OPEN,
    CALLBACK_INFO_PAYMENT,
    info_back_keyboard,
    info_menu_keyboard,
)
from app.models.enums import CityChoice
from app.models.user import User
from app.services.localization import LocalizationService
from app.services.user import UserService
from app.utils.html import e

logger = logging.getLogger(__name__)

router = Router(name="user_info")

_TOPIC_KEYS = {
    "delivery": "delivery",
    "payment": "payment",
    "contacts": "contacts",
}


def _city_bucket(user: User) -> str:
    if user.selected_city == CityChoice.BERLIN:
        return "berlin"
    return "other"


def _city_label(i18n: LocalizationService, user: User) -> str:
    if user.selected_city == CityChoice.BERLIN:
        return i18n.t("city.berlin")
    return i18n.t("city.delivery")


def _info_intro(i18n: LocalizationService, user: User) -> str:
    return (
        f"{i18n.t('info.title')}\n\n"
        f"{i18n.t('info.intro', city=e(_city_label(i18n, user)))}"
    )


def _topic_text(i18n: LocalizationService, user: User, topic: str) -> str:
    bucket = _city_bucket(user)
    return i18n.t(f"info.{bucket}.{topic}")


async def _render_info_menu(
    *,
    message: Message,
    user: User,
    i18n: LocalizationService,
    edit: bool = False,
) -> None:
    text = _info_intro(i18n, user)
    markup = info_menu_keyboard(i18n)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _render_topic(
    *,
    message: Message,
    user: User,
    i18n: LocalizationService,
    topic: str,
    edit: bool = False,
) -> None:
    text = _topic_text(i18n, user, topic)
    markup = info_back_keyboard(i18n)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.message(LocalizedText("menu.info"))
async def open_info(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    ready = await ensure_onboarded_user(message, session, state)
    if ready is None:
        return
    user, i18n = ready
    await _render_info_menu(message=message, user=user, i18n=i18n, edit=False)


@router.callback_query(F.data == CALLBACK_INFO_OPEN)
async def info_open_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    user = await UserService(session).ensure_user(callback.from_user)
    localized = LocalizationService.from_user(user)
    await callback.answer()
    try:
        await _render_info_menu(
            message=callback.message,
            user=user,
            i18n=localized,
            edit=True,
        )
    except TelegramBadRequest:
        await _render_info_menu(
            message=callback.message,
            user=user,
            i18n=localized,
            edit=False,
        )


@router.callback_query(
    F.data.in_({CALLBACK_INFO_DELIVERY, CALLBACK_INFO_PAYMENT, CALLBACK_INFO_CONTACTS})
)
async def info_topic_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        await callback.answer()
        return

    topic = callback.data.removeprefix("info:")
    if topic not in _TOPIC_KEYS:
        await callback.answer(i18n.t("error.invalid_callback"), show_alert=True)
        return

    user = await UserService(session).ensure_user(callback.from_user)
    localized = LocalizationService.from_user(user)
    await callback.answer()
    try:
        await _render_topic(
            message=callback.message,
            user=user,
            i18n=localized,
            topic=topic,
            edit=True,
        )
    except TelegramBadRequest:
        await _render_topic(
            message=callback.message,
            user=user,
            i18n=localized,
            topic=topic,
            edit=False,
        )


@router.callback_query(F.data == CALLBACK_INFO_CHANGE_LANGUAGE)
async def info_change_language(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: LocalizationService,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    from app.handlers.user.start import _ask_language

    await callback.answer()
    await _ask_language(callback.message, i18n, state)


@router.callback_query(F.data == CALLBACK_INFO_CHANGE_CITY)
async def info_change_city(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    i18n: LocalizationService,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    user = await UserService(session).ensure_user(callback.from_user)
    localized = LocalizationService.from_user(user)

    from app.handlers.user.start import _ask_city

    await callback.answer()
    await _ask_city(callback.message, localized, state)
