"""Confirm-once guard for FSM wizards (anti double-submit)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiogram.fsm.context import FSMContext

from app.utils.concurrency import keyed_lock


@asynccontextmanager
async def confirm_once(
    state: FSMContext,
    *,
    lock_key: str | None = None,
) -> AsyncIterator[dict[str, Any] | None]:
    """
    Yield FSM data when this confirm is the first submission; otherwise ``None``.

    Sets ``submitted=True`` before yielding. On exception inside the ``with``
    block, resets ``submitted=False`` so the user can retry.
    """
    if lock_key is not None:
        async with keyed_lock(lock_key):
            data = await state.get_data()
            if data.get("submitted"):
                yield None
                return
            await state.update_data(submitted=True)
            try:
                yield await state.get_data()
            except Exception:
                await state.update_data(submitted=False)
                raise
        return

    data = await state.get_data()
    if data.get("submitted"):
        yield None
        return
    await state.update_data(submitted=True)
    try:
        yield await state.get_data()
    except Exception:
        await state.update_data(submitted=False)
        raise
