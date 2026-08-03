"""Admin settings section (Reply Keyboard entry)."""

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from app.filters.localized_text import LocalizedText
from app.keyboards.admin import admin_menu_keyboard
from app.services.localization import LocalizationService
from app.states.admin import ADMIN_WIZARD_STATES

router = Router(name="admin_settings")


@router.message(LocalizedText("admin.menu_settings"), ~StateFilter(*ADMIN_WIZARD_STATES))
async def open_settings(message: Message, i18n: LocalizationService) -> None:
    await message.answer(
        i18n.t("admin.section_settings"),
        reply_markup=admin_menu_keyboard(i18n),
    )
