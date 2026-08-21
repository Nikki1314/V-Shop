"""Admin broadcast: compose (text/photo) → preview → confirm → send with progress."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters.localized_text import LocalizedText
from app.keyboards.admin import admin_cancel_keyboard, admin_menu_keyboard
from app.keyboards.admin_broadcast import (
    CALLBACK_BROADCAST_CANCEL,
    CALLBACK_BROADCAST_CONFIRM,
    CALLBACK_BROADCAST_START,
    broadcast_actions_keyboard,
    broadcast_confirm_keyboard,
)
from app.services.admin import AdminService
from app.services.broadcast import BroadcastResult, BroadcastService
from app.services.localization import LocalizationService
from app.states.admin import ADMIN_WIZARD_STATES, BroadcastStates
from app.utils.confirm import confirm_once
from app.utils.telegram_ui import as_message, clear_inline_markup

logger = logging.getLogger(__name__)

router = Router(name="admin_broadcast")

_FAILED_IDS_PREVIEW_LIMIT = 30


def _preview_meta(i18n: LocalizationService, data: dict[str, Any], recipients: int) -> str:
    has_photo = bool(data.get("photo_file_id"))
    text = data.get("text") or ""
    kind = (
        i18n.t("admin.broadcast_kind_photo_text")
        if has_photo and text
        else (
            i18n.t("admin.broadcast_kind_photo")
            if has_photo
            else i18n.t("admin.broadcast_kind_text")
        )
    )
    return i18n.t(
        "admin.broadcast_preview_meta",
        kind=kind,
        recipients=recipients,
        chars=len(text),
    )


async def _send_preview(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
    *,
    recipients: int,
) -> None:
    data = await state.get_data()
    await state.set_state(BroadcastStates.preview)
    meta = _preview_meta(i18n, data, recipients)
    markup = broadcast_confirm_keyboard(i18n)
    photo_id = data.get("photo_file_id")
    text = data.get("text")

    await message.answer(meta)
    if photo_id:
        caption = (text or "")[:1024] or None
        try:
            await message.answer_photo(
                photo=photo_id,
                caption=caption,
                reply_markup=markup,
            )
            if text and len(text) > 1024:
                await message.answer(text)
            return
        except Exception:
            logger.debug("Could not send broadcast preview photo", exc_info=True)

    await message.answer(
        text or i18n.t("admin.broadcast_empty_body"),
        reply_markup=markup,
    )


async def _cancel_broadcast(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(
        i18n.t("admin.broadcast_cancelled"),
        reply_markup=admin_menu_keyboard(i18n),
    )


def _format_failed_users(i18n: LocalizationService, failed: list[int]) -> str:
    if not failed:
        return i18n.t("admin.broadcast_failed_none")
    shown = failed[:_FAILED_IDS_PREVIEW_LIMIT]
    lines = ", ".join(f"<code>{chat_id}</code>" for chat_id in shown)
    extra = len(failed) - len(shown)
    text = i18n.t("admin.broadcast_failed_list", ids=lines, count=len(failed))
    if extra > 0:
        text += "\n" + i18n.t("admin.broadcast_failed_more", extra=extra)
    return text


# ---------------------------------------------------------------------------
# Section entry
# ---------------------------------------------------------------------------


@router.message(LocalizedText("admin.menu_broadcast"), ~StateFilter(*ADMIN_WIZARD_STATES))
async def open_broadcast(
    message: Message,
    i18n: LocalizationService,
    session: AsyncSession,
) -> None:
    count = await AdminService(session).count_users()
    await message.answer(
        i18n.t("admin.section_broadcast"),
        reply_markup=admin_menu_keyboard(i18n),
    )
    await message.answer(
        i18n.t("admin.broadcast_actions", recipients=count),
        reply_markup=broadcast_actions_keyboard(i18n),
    )


@router.callback_query(F.data == CALLBACK_BROADCAST_START)
async def start_broadcast(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await callback.answer()
    message = as_message(callback)
    if message is None:
        return
    await state.clear()
    await state.set_state(BroadcastStates.compose)
    await message.answer(
        i18n.t("admin.broadcast_ask_content"),
        reply_markup=admin_cancel_keyboard(i18n),
    )


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@router.message(StateFilter(BroadcastStates), LocalizedText("common.cancel"))
async def cancel_broadcast_message(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await _cancel_broadcast(message, i18n, state)


@router.callback_query(StateFilter(BroadcastStates), F.data == CALLBACK_BROADCAST_CANCEL)
async def cancel_broadcast_callback(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
) -> None:
    await callback.answer()
    message = as_message(callback)
    if message is None:
        return
    await _cancel_broadcast(message, i18n, state)


# ---------------------------------------------------------------------------
# Compose → preview
# ---------------------------------------------------------------------------


@router.message(StateFilter(BroadcastStates.compose), F.photo)
async def compose_photo(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not message.photo:
        return
    photo = message.photo[-1]
    caption = (message.caption or "").strip() or None
    await state.update_data(photo_file_id=photo.file_id, text=caption)
    recipients = await AdminService(session).count_users()
    await message.answer(
        i18n.t("admin.broadcast_got_photo"),
        reply_markup=admin_cancel_keyboard(i18n),
    )
    await _send_preview(message, i18n, state, recipients=recipients)


@router.message(StateFilter(BroadcastStates.compose), F.text)
async def compose_text(
    message: Message,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(
            i18n.t("admin.broadcast_content_invalid"),
            reply_markup=admin_cancel_keyboard(i18n),
        )
        return
    await state.update_data(text=text, photo_file_id=None)
    recipients = await AdminService(session).count_users()
    await _send_preview(message, i18n, state, recipients=recipients)


@router.message(StateFilter(BroadcastStates.compose))
async def compose_invalid(message: Message, i18n: LocalizationService) -> None:
    await message.answer(
        i18n.t("admin.broadcast_content_invalid"),
        reply_markup=admin_cancel_keyboard(i18n),
    )


@router.message(StateFilter(BroadcastStates.preview))
async def preview_waiting(message: Message, i18n: LocalizationService) -> None:
    await message.answer(i18n.t("admin.broadcast_confirm_waiting"))


# ---------------------------------------------------------------------------
# Confirm → send
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(BroadcastStates.preview),
    F.data == CALLBACK_BROADCAST_CONFIRM,
)
async def confirm_broadcast(
    callback: CallbackQuery,
    i18n: LocalizationService,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await callback.answer()
    message = as_message(callback)
    if message is None or callback.from_user is None:
        return

    # Claim under lock only; fan-out must not hold the process lock.
    text: str | None = None
    photo_file_id: str | None = None
    recipients: list[int] = []

    async with confirm_once(state, lock_key=f"broadcast:{callback.from_user.id}") as data:
        if data is None:
            return

        text = data.get("text")
        photo_file_id = data.get("photo_file_id")
        if not text and not photo_file_id:
            await state.clear()
            await message.answer(
                i18n.t("admin.broadcast_empty_body"),
                reply_markup=admin_menu_keyboard(i18n),
            )
            return

        recipients = await AdminService(session).list_broadcast_recipient_ids()
        if not recipients:
            await state.clear()
            await message.answer(
                i18n.t("admin.broadcast_no_recipients"),
                reply_markup=admin_menu_keyboard(i18n),
            )
            return

        # Release the DB transaction before the long Telegram fan-out.
        await session.commit()
        await clear_inline_markup(message)
        await state.clear()

    progress_message = await message.answer(
        i18n.t(
            "admin.broadcast_progress",
            sent=0,
            failed=0,
            total=len(recipients),
            percent=0,
        ),
        reply_markup=admin_menu_keyboard(i18n),
    )

    async def on_progress(sent: int, failed: int, total: int) -> None:
        percent = int((sent + failed) * 100 / total) if total else 100
        try:
            await progress_message.edit_text(
                i18n.t(
                    "admin.broadcast_progress",
                    sent=sent,
                    failed=failed,
                    total=total,
                    percent=percent,
                )
            )
        except Exception:
            logger.debug("Could not update broadcast progress", exc_info=True)

    result: BroadcastResult = await BroadcastService(bot).send(
        recipients,
        text=text,
        photo_file_id=photo_file_id,
        on_progress=on_progress,
        progress_every=max(1, min(10, len(recipients) // 10 or 1)),
    )

    summary = i18n.t(
        "admin.broadcast_done",
        sent=result.sent,
        failed=result.failed_count,
        total=result.total,
    )
    failed_block = _format_failed_users(i18n, result.failed)
    await message.answer(
        f"{summary}\n\n{failed_block}",
        reply_markup=admin_menu_keyboard(i18n),
    )
