"""Admin domain exceptions."""

from __future__ import annotations


class ProductInUseError(Exception):
    """Raised when a product cannot be deleted because of order history."""


class CategoryInUseError(Exception):
    """Raised when a category cannot be deleted because it still has products."""
