"""Admin FSM states."""

from aiogram.fsm.state import State, StatesGroup


class AddProductStates(StatesGroup):
    photo = State()
    name_ru = State()
    name_en = State()
    name_de = State()
    description_ru = State()
    description_en = State()
    description_de = State()
    category = State()
    flavor = State()
    volume = State()
    nicotine_strength = State()
    price = State()
    confirmation = State()


class EditProductStates(StatesGroup):
    photo = State()
    name_ru = State()
    name_en = State()
    name_de = State()
    description_ru = State()
    description_en = State()
    description_de = State()
    category = State()
    flavor = State()
    volume = State()
    nicotine_strength = State()
    price = State()
    confirmation = State()


class EditPriceStates(StatesGroup):
    price = State()


class EditDescriptionStates(StatesGroup):
    description_ru = State()
    description_en = State()
    description_de = State()


class CreateCategoryStates(StatesGroup):
    name = State()


class RenameCategoryStates(StatesGroup):
    name = State()


class SearchOrderStates(StatesGroup):
    query = State()


class BroadcastStates(StatesGroup):
    compose = State()
    preview = State()


# Used to exclude admin menu handlers while any product wizard is active.
PRODUCT_WIZARD_STATES = (
    AddProductStates,
    EditProductStates,
    EditPriceStates,
    EditDescriptionStates,
)

CATEGORY_WIZARD_STATES = (
    CreateCategoryStates,
    RenameCategoryStates,
)

ORDER_WIZARD_STATES = (SearchOrderStates,)

BROADCAST_WIZARD_STATES = (BroadcastStates,)

# Exclude reply-menu handlers while any admin wizard is active.
ADMIN_WIZARD_STATES = (
    PRODUCT_WIZARD_STATES
    + CATEGORY_WIZARD_STATES
    + ORDER_WIZARD_STATES
    + BROADCAST_WIZARD_STATES
)

