"""
What the product edit wizard collects, it must save.

Found in review: the wizard asks for all four names and descriptions, shows them
in the preview, and then writes only three of each — the Ukrainian edits were
silently discarded. Separately, changing a product's category left
``subcategory_id`` pointing at a brand of the *old* category, so the product's
two parents disagreed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.handlers.admin.product_manage.handlers import confirm_edit_product
from app.models.product import Product
from app.services.admin import AdminService
from app.services.localization import LocalizationService

ADMIN_ID = 991001


class SpyMessage(Message):
    model_config = {"extra": "allow"}

    async def answer(self, text: str, **kwargs: Any) -> Any:
        self.__dict__.setdefault("sent", []).append(text)
        return self

    async def answer_photo(self, *args: Any, **kwargs: Any) -> Any:
        return self

    async def edit_reply_markup(self, **kwargs: Any) -> Any:
        return self


class SpyCallback(CallbackQuery):
    model_config = {"extra": "allow"}

    async def answer(self, text: str | None = None, **kwargs: Any) -> Any:
        return True


def admin_callback() -> SpyCallback:
    message = SpyMessage(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=ADMIN_ID, type="private"),
        from_user=TgUser(id=1, is_bot=True, first_name="VShop"),
        text="preview",
    )
    return SpyCallback(
        id="c1",
        from_user=TgUser(id=ADMIN_ID, is_bot=False, first_name="Admin"),
        chat_instance="ci",
        data="admin:product:econfirm",
        message=message,
    )


async def build_catalog(session: AsyncSession):  # type: ignore[no-untyped-def]
    """Two categories, each with its own brand, and a product in the first."""
    admin = AdminService(session)
    first = await admin.create_category(
        "Liquids",
        name_ru="Жидкости",
        name_en="Liquids",
        name_de="Liquids",
        name_uk="Рідини",
    )
    second = await admin.create_category(
        "Hardware",
        name_ru="Устройства",
        name_en="Hardware",
        name_de="Geräte",
        name_uk="Пристрої",
    )
    await session.flush()
    brand_one = await admin.create_subcategory(
        category_id=first.id,
        name="Nasty",
        name_ru="Nasty",
        name_en="Nasty",
        name_de="Nasty",
        name_uk="Nasty",
    )
    brand_two = await admin.create_subcategory(
        category_id=second.id,
        name="Vaporesso",
        name_ru="Vaporesso",
        name_en="Vaporesso",
        name_de="Vaporesso",
        name_uk="Vaporesso",
    )
    await session.flush()
    product = await admin.create_product(
        category_id=first.id,
        subcategory_id=brand_one.id,
        name_ru="Старое",
        name_en="Old",
        name_de="Alt",
        name_uk="Старе",
        description_ru="о",
        description_en="o",
        description_de="a",
        description_uk="с",
        flavor="Mango",
        volume="30ml",
        nicotine_strength="3mg",
        price=Decimal("10.00"),
    )
    await session.flush()
    return product, first, second, brand_one, brand_two


def edit_state(product_id: int, category_id: int, **overrides: Any) -> tuple[FSMContext, dict]:
    data = {
        "product_id": product_id,
        "category_id": category_id,
        "category_name": "Liquids",
        "name_ru": "Новое",
        "name_en": "New",
        "name_de": "Neu",
        "name_uk": "Нове",
        "description_ru": "н",
        "description_en": "n",
        "description_de": "n",
        "description_uk": "н",
        "flavor": "Berry",
        "volume": "60ml",
        "nicotine_strength": "6mg",
        "price": "19.99",
        "page": 0,
    }
    data.update(overrides)
    state = FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=ADMIN_ID, user_id=ADMIN_ID),
    )
    return state, data


@pytest.mark.asyncio
async def test_editing_a_product_saves_the_ukrainian_name_and_description(
    session: AsyncSession,
) -> None:
    """
    Regression: the wizard collected uk and the confirm step dropped it.

    The admin typed a Ukrainian name, saw it in the preview, got "product
    updated", and the old value was still in the database.
    """
    product, first, _second, _b1, _b2 = await build_catalog(session)
    state, data = edit_state(product.id, first.id)
    await state.set_data(data)

    await confirm_edit_product(
        admin_callback(),
        LocalizationService("en"),
        state,
        session,  # type: ignore[arg-type]
    )
    await session.flush()

    saved = await session.scalar(select(Product).where(Product.id == product.id))
    assert saved is not None
    assert saved.name_uk == "Нове", "the Ukrainian name was discarded"
    assert saved.description_uk == "н", "the Ukrainian description was discarded"
    # the other three must still be written, as before
    assert (saved.name_ru, saved.name_en, saved.name_de) == ("Новое", "New", "Neu")


@pytest.mark.asyncio
async def test_editing_a_product_keeps_its_two_parents_consistent(
    session: AsyncSession,
) -> None:
    """
    Regression: moving a product to another category kept the old brand.

    The product then claimed a category it did not belong to through its brand,
    which is exactly the state the catalog hierarchy and the visibility rule
    both assume cannot happen.
    """
    product, _first, second, _brand_one, brand_two = await build_catalog(session)
    state, data = edit_state(
        product.id, second.id, subcategory_id=brand_two.id, category_name="Hardware"
    )
    await state.set_data(data)

    await confirm_edit_product(
        admin_callback(),
        LocalizationService("en"),
        state,
        session,  # type: ignore[arg-type]
    )
    await session.flush()

    saved = await session.scalar(select(Product).where(Product.id == product.id))
    assert saved is not None
    assert saved.category_id == second.id
    assert saved.subcategory_id == brand_two.id, "the brand did not move with the category"

    brand = await AdminService(session).get_subcategory(saved.subcategory_id or 0)
    assert brand is not None
    assert brand.category_id == saved.category_id, (
        "the product's brand belongs to a different category than the product"
    )


@pytest.mark.asyncio
async def test_an_edit_that_does_not_move_the_product_keeps_its_brand(
    session: AsyncSession,
) -> None:
    """Editing text alone must not disturb either parent."""
    product, first, _second, brand_one, _brand_two = await build_catalog(session)
    state, data = edit_state(product.id, first.id, subcategory_id=brand_one.id)
    await state.set_data(data)

    await confirm_edit_product(
        admin_callback(),
        LocalizationService("en"),
        state,
        session,  # type: ignore[arg-type]
    )
    await session.flush()

    saved = await session.scalar(select(Product).where(Product.id == product.id))
    assert saved is not None
    assert saved.category_id == first.id
    assert saved.subcategory_id == brand_one.id
    assert saved.flavor == "Berry" and str(saved.price) == "19.99"


def test_every_field_the_edit_wizard_collects_is_written() -> None:
    """
    Guard the class of bug, not just the two instances.

    A step added to the wizard that nobody wires into the update call looks like
    it works — the preview shows the new value and the bot confirms the save.
    """
    import ast
    import pathlib

    from app.handlers.admin.product_manage.common import EDIT_TEXT_STEPS

    collected = {meta[0] for meta in EDIT_TEXT_STEPS.values()}

    source = pathlib.Path("app/handlers/admin/product_manage/handlers.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    written: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "confirm_edit_product":
            continue
        # Fields reach update_product either as keyword arguments or as keys of
        # a dict splatted into it; count both, so the guard does not depend on
        # which style the handler happens to use.
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "update_product"
            ):
                written |= {kw.arg for kw in inner.keywords if kw.arg}
            if isinstance(inner, ast.Dict):
                written |= {
                    key.value
                    for key in inner.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
            if (
                isinstance(inner, ast.Subscript)
                and isinstance(inner.slice, ast.Constant)
                and isinstance(inner.slice.value, str)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "fields"
            ):
                written.add(inner.slice.value)

    missing = sorted(collected - written)
    assert missing == [], (
        f"the edit wizard collects {missing} but confirm_edit_product never "
        "writes them — the admin's edits are silently discarded"
    )
