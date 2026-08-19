"""Checkout FSM states."""

from aiogram.fsm.state import State, StatesGroup


class CheckoutStates(StatesGroup):
    customer_name = State()
    delivery_type = State()
    address = State()
    preferred_time = State()
    contact = State()
    payment_method = State()
    confirmation = State()
