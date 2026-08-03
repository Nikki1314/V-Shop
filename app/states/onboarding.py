"""Onboarding FSM states."""

from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    language = State()
    city = State()
