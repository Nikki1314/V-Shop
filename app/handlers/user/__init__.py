"""User-facing handlers."""

from aiogram import Router

from . import admin_guard, cart, catalog, checkout, info, start


def get_user_router() -> Router:
    """Aggregate user routers."""
    router = Router(name="user")
    # start first so /start wins; menu navigation routers next
    router.include_router(start.router)
    router.include_router(catalog.router)
    router.include_router(cart.router)
    router.include_router(checkout.router)
    router.include_router(info.router)
    # Non-admin /admin denial (must not be behind admin router filters)
    router.include_router(admin_guard.router)
    return router
