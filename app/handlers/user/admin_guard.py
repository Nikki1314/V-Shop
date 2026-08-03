"""Reject unauthorized /admin attempts without exposing admin features."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.filters.admin import IsNotAdmin
from app.services.localization import LocalizationService

router = Router(name="user_admin_guard")


@router.message(Command("admin"), IsNotAdmin())
async def admin_access_denied(message: Message, i18n: LocalizationService) -> None:
    """
    Reply to non-admins who try ``/admin``.

    They must not receive the admin panel or any admin controls.
    """
    await message.answer(i18n.t("admin.access_denied"))
