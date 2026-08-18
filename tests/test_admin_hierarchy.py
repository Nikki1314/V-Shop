"""Admin panel wiring for the catalog hierarchy: keyboards, callbacks, states."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.admin_categories import (
    CALLBACK_CATEGORY_EDIT_PREFIX,
    CALLBACK_CATEGORY_NAME_PREFIX,
    CALLBACK_CATEGORY_TOGGLE_PREFIX,
    category_language_keyboard,
    category_manage_keyboard,
)
from app.keyboards.admin_subcategories import (
    CALLBACK_SUB_ASSIGN_TO_PREFIX,
    CALLBACK_SUB_CREATE_PREFIX,
    CALLBACK_SUB_DELETE_PREFIX,
    CALLBACK_SUB_LIST_PREFIX,
    CALLBACK_SUB_NAME_PREFIX,
    CALLBACK_SUB_VIEW_PREFIX,
    subcategories_list_keyboard,
    subcategory_assign_keyboard,
    subcategory_language_keyboard,
    subcategory_manage_keyboard,
)
from app.models.category import Subcategory
from app.services.admin import AdminService, SubcategoryInUseError
from app.services.localization import LocalizationService
from app.states.admin import (
    ADMIN_WIZARD_STATES,
    CreateCategoryStates,
    CreateSubcategoryStates,
    RenameCategoryStates,
    RenameSubcategoryStates,
)
from app.utils.cache import invalidate_categories_cache

LANGS = ("ru", "en", "de", "uk")
PRODUCT_DEFAULTS = dict(
    name_en="P", name_de="P", description_ru="d", description_en="d",
    description_de="d", flavor="f", volume="30ml", nicotine_strength="3mg",
    price=Decimal("10.00"),
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_categories_cache()


def _buttons(markup) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


# ------------------------------------------------------------ FSM wiring


def test_every_new_wizard_is_registered_in_the_guard() -> None:
    """Unregistered wizards get corrupted by admin menu taps."""
    for group in (
        CreateCategoryStates,
        RenameCategoryStates,
        CreateSubcategoryStates,
        RenameSubcategoryStates,
    ):
        assert group in ADMIN_WIZARD_STATES, f"{group.__name__} not guarded"


def test_create_wizards_collect_all_four_languages() -> None:
    for group in (CreateCategoryStates, CreateSubcategoryStates):
        states = {s.state.split(":")[-1] for s in group.__all_states__}
        assert states == {f"name_{code}" for code in LANGS}, group.__name__


# -------------------------------------------------------------- keyboards


@pytest.mark.asyncio
async def test_category_card_exposes_every_required_action(
    session: AsyncSession,
) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()
    i18n = LocalizationService.from_code("en")

    payloads = [
        data
        for _, data in _buttons(
            category_manage_keyboard(i18n, category, index=0, total=2, subcategory_count=3)
        )
    ]
    assert f"{CALLBACK_CATEGORY_EDIT_PREFIX}{category.id}" in payloads   # edit
    assert f"{CALLBACK_CATEGORY_TOGGLE_PREFIX}{category.id}" in payloads  # activate
    assert f"admin:sub:list:{category.id}" in payloads                   # brands
    assert any(d.startswith("admin:cat:del:") for d in payloads)         # delete
    assert any(d.startswith("admin:cat:down:") for d in payloads)        # reorder


@pytest.mark.asyncio
async def test_category_toggle_label_follows_state(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()
    i18n = LocalizationService.from_code("en")

    active = dict(_buttons(category_manage_keyboard(i18n, category, index=0, total=1)))
    assert i18n.t("admin.category_deactivate") in active

    await admin.set_category_active(category, False)
    hidden = dict(_buttons(category_manage_keyboard(i18n, category, index=0, total=1)))
    assert i18n.t("admin.category_activate") in hidden


def test_language_pickers_offer_all_four_languages() -> None:
    i18n = LocalizationService.from_code("uk")

    cat = _buttons(category_language_keyboard(i18n, 7))
    assert [d for _, d in cat][:4] == [
        f"{CALLBACK_CATEGORY_NAME_PREFIX}7:{code}" for code in LANGS
    ]
    assert [t for t, _ in cat][:4] == [i18n.t(f"language.{c}") for c in LANGS]

    sub = _buttons(subcategory_language_keyboard(i18n, 9))
    assert [d for _, d in sub][:4] == [
        f"{CALLBACK_SUB_NAME_PREFIX}9:{code}" for code in LANGS
    ]


@pytest.mark.asyncio
async def test_subcategory_card_exposes_every_required_action(
    session: AsyncSession,
) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    sub = await admin.create_subcategory(category_id=category.id, name="Brand A")
    await session.flush()
    i18n = LocalizationService.from_code("en")

    payloads = [
        d for _, d in _buttons(subcategory_manage_keyboard(i18n, sub, index=0, total=2))
    ]
    assert any(d.startswith("admin:sub:edit:") for d in payloads)   # edit
    assert any(d.startswith("admin:sub:act:") for d in payloads)    # activate
    assert any(d.startswith("admin:sub:down:") for d in payloads)   # reorder
    assert any(d.startswith("admin:sub:asg:") for d in payloads)    # assign
    assert any(d.startswith(CALLBACK_SUB_DELETE_PREFIX) for d in payloads)
    assert f"{CALLBACK_SUB_LIST_PREFIX}{category.id}" in payloads   # back


@pytest.mark.asyncio
async def test_brand_list_marks_hidden_brands(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    live = await admin.create_subcategory(category_id=category.id, name="Live")
    hidden = await admin.create_subcategory(category_id=category.id, name="Hidden")
    await admin.set_subcategory_active(hidden, False)
    await session.flush()
    i18n = LocalizationService.from_code("en")

    labels = dict(
        (d, t)
        for t, d in _buttons(
            subcategories_list_keyboard(i18n, category.id, [live, hidden])
        )
    )
    assert i18n.t("admin.subcategory_status_active") in labels[
        f"{CALLBACK_SUB_VIEW_PREFIX}{live.id}"
    ]
    assert i18n.t("admin.subcategory_status_inactive") in labels[
        f"{CALLBACK_SUB_VIEW_PREFIX}{hidden.id}"
    ]
    assert f"{CALLBACK_SUB_CREATE_PREFIX}{category.id}" in labels


@pytest.mark.asyncio
async def test_assign_keyboard_omits_the_current_category(
    session: AsyncSession,
) -> None:
    admin = AdminService(session)
    home = await admin.create_category("Liquids")
    other = await admin.create_category("Disposables")
    sub = await admin.create_subcategory(category_id=home.id, name="Brand A")
    await session.flush()
    i18n = LocalizationService.from_code("en")

    payloads = [
        d
        for _, d in _buttons(
            subcategory_assign_keyboard(i18n, sub, [home, other])
        )
    ]
    assert f"{CALLBACK_SUB_ASSIGN_TO_PREFIX}{sub.id}:{other.id}" in payloads
    assert f"{CALLBACK_SUB_ASSIGN_TO_PREFIX}{sub.id}:{home.id}" not in payloads


def test_callback_payloads_fit_telegram_limit() -> None:
    """Telegram rejects callback_data longer than 64 bytes."""
    i18n = LocalizationService.from_code("ru")
    sub = Subcategory(
        id=999999, category_id=888888, name_ru="Б", name_en="B",
        name_de="B", name_uk="Б", sort_order=0, is_active=True,
    )
    markups = [
        subcategory_manage_keyboard(i18n, sub, index=1, total=5),
        subcategory_language_keyboard(i18n, 999999),
        category_language_keyboard(i18n, 999999),
    ]
    for markup in markups:
        for _, data in _buttons(markup):
            assert len(data.encode()) <= 64, data


# ------------------------------------------------- admin operations e2e


@pytest.mark.asyncio
async def test_full_subcategory_lifecycle_through_the_service(
    session: AsyncSession,
) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    other = await admin.create_category("Disposables")

    sub = await admin.create_subcategory(
        category_id=category.id, name="Brand A",
        name_ru="Бренд", name_en="Brand A", name_de="Marke A", name_uk="Бренд А",
    )
    await session.flush()
    assert sub.name_uk == "Бренд А"

    await admin.set_subcategory_names(sub, name_de="Marke B")
    assert sub.name_de == "Marke B"
    assert sub.name_uk == "Бренд А"

    await admin.set_subcategory_active(sub, False)
    assert sub.is_active is False

    await admin.reassign_subcategory(sub, other.id)
    await session.flush()
    assert sub.category_id == other.id
    assert [s.id for s in await admin.list_subcategories(category.id)] == []

    await admin.delete_subcategory(sub)
    await session.flush()
    assert await admin.get_subcategory(sub.id) is None


@pytest.mark.asyncio
async def test_reordering_brands_within_a_category(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    a = await admin.create_subcategory(category_id=category.id, name="A")
    await admin.create_subcategory(category_id=category.id, name="B")
    c = await admin.create_subcategory(category_id=category.id, name="C")
    await session.flush()

    await admin.move_subcategory(category.id, c.id, direction=-1)
    assert [s.name_en for s in await admin.list_subcategories(category.id)] == [
        "A", "C", "B",
    ]
    await admin.move_subcategory(category.id, a.id, direction=1)
    assert [s.name_en for s in await admin.list_subcategories(category.id)] == [
        "C", "A", "B",
    ]


@pytest.mark.asyncio
async def test_brand_with_products_cannot_be_deleted_from_admin(
    session: AsyncSession,
) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    sub = await admin.create_subcategory(category_id=category.id, name="Brand A")
    await session.flush()
    await admin.create_product(
        category_id=category.id, subcategory_id=sub.id, name_ru="Mango",
        **PRODUCT_DEFAULTS,
    )
    await session.flush()

    with pytest.raises(SubcategoryInUseError):
        await admin.delete_subcategory(sub)


@pytest.mark.asyncio
async def test_category_names_editable_per_language(session: AsyncSession) -> None:
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()

    await admin.set_category_names(category, name_uk="Рідини")
    await admin.set_category_names(category, name_de="Liquids DE")

    assert category.name_uk == "Рідини"
    assert category.name_de == "Liquids DE"
    assert category.name_en == "Liquids"
    # legacy column tracks Russian so existing rendering keeps working
    await admin.set_category_names(category, name_ru="Жидкости")
    assert category.name == "Жидкости"


# ------------------------------------------- existing product management


@pytest.mark.asyncio
async def test_product_management_still_works(session: AsyncSession) -> None:
    """The product wizard predates the hierarchy and must be unaffected."""
    admin = AdminService(session)
    category = await admin.create_category("Liquids")
    await session.flush()

    product = await admin.create_product(
        category_id=category.id, name_ru="Mango", **PRODUCT_DEFAULTS
    )
    await session.flush()

    assert product.category_id == category.id
    assert product.subcategory_id is None  # wizard does not collect one yet

    await admin.set_product_price(product, Decimal("15.00"))
    assert product.price == Decimal("15.00")

    await admin.disable_product(product)
    assert product.is_active is False
    await admin.enable_product(product)
    assert product.is_active is True

    listed = await admin.list_products()
    assert [p.id for p in listed] == [product.id]


@pytest.mark.asyncio
async def test_create_category_accepts_all_four_names_through_the_facade(
    session: AsyncSession,
) -> None:
    """Regression: the façade once rejected the localized kwargs with TypeError."""
    admin = AdminService(session)
    category = await admin.create_category(
        "Liquids",
        name_ru="Жидкости",
        name_en="Liquids",
        name_de="Liquids DE",
        name_uk="Рідини",
    )
    await session.flush()

    assert category.name_ru == "Жидкости"
    assert category.name_en == "Liquids"
    assert category.name_de == "Liquids DE"
    assert category.name_uk == "Рідини"
    assert category.name == "Liquids"  # legacy column takes the positional name


def test_admin_handler_modules_import_cleanly() -> None:
    """Undefined names in handlers only surface at import/runtime."""
    import importlib

    for module in (
        "app.handlers.admin.categories",
        "app.handlers.admin.subcategories",
        "app.keyboards.admin_categories",
        "app.keyboards.admin_subcategories",
    ):
        assert importlib.import_module(module) is not None


def test_no_undefined_names_in_admin_handlers() -> None:
    """Every global a handler references must exist on its module.

    Catches the class of bug where a patch introduces `e(...)` or `message`
    without the corresponding import or assignment — a runtime NameError that
    unit tests of the service layer never reach.
    """
    import builtins
    import importlib
    import pathlib as _pathlib
    import symtable

    for path in sorted(_pathlib.Path("app/handlers/admin").rglob("*.py")):
        dotted = path.with_suffix("").as_posix().replace("/", ".")
        module = importlib.import_module(dotted)
        table = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
        for func in table.get_children():
            for sym in func.get_symbols():
                name = sym.get_name()
                if not sym.is_global() or sym.is_assigned():
                    continue
                assert hasattr(module, name) or hasattr(builtins, name), (
                    f"{path}: undefined global {name!r}"
                )
