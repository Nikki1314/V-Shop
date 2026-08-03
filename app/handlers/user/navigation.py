"""Shared helpers for user navigation handlers."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.handlers.user.start import _continue_onboarding
from app.keyboards.reply import main_menu_keyboard
from app.models.user import User
from app.services.localization import LocalizationService
from app.services.user import UserService


async def ensure_onboarded_user(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> tuple[User, LocalizationService] | None:
    """
    Ensure the sender finished onboarding.

    Returns ``(user, i18n)`` when ready; otherwise resumes onboarding and
    returns ``None``.
    """
    if message.from_user is None:
        return None

    service = UserService(session)
    user = await service.ensure_user(message.from_user)
    i18n = LocalizationService.from_user(user)

    if not UserService.is_onboarded(user):
        await _continue_onboarding(message, user, i18n, state)
        return None

    return user, i18n


async def answer_with_menu(message: Message, text: str, i18n: LocalizationService) -> None:
    """Reply while keeping the localized main Reply Keyboard attached."""
    await message.answer(text, reply_markup=main_menu_keyboard(i18n))
