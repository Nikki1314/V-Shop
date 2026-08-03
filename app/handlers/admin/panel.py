"""Admin panel entry — authorized users only."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.keyboards.admin import admin_menu_keyboard
from app.services.localization import LocalizationService

router = Router(name="admin_panel")


async def show_admin_menu(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext | None = None,
) -> None:
    """Show the admin Reply Keyboard menu."""
    if state is not None:
        await state.clear()
    await message.answer(
        i18n.t("admin.panel_ready"),
        reply_markup=admin_menu_keyboard(i18n),
    )


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    """
    Open the admin panel.

    Authorization is enforced by the parent admin router (filter + middleware).
    Non-admins never reach this handler.
    """
    await show_admin_menu(message, i18n, state)
