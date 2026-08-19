"""One definition of what makes a product visible to customers.

A product is on sale when it is active *and* nothing above it in the hierarchy
is hidden. Deactivating a brand or a whole category must take its products off
the shelf without touching each product row.

The category is checked through ``products.category_id``, which is ``NOT NULL``
on every row and which ``move_to_subcategory`` keeps in step with the brand's
category. That covers both shapes in one join: hierarchy products and the
pre-hierarchy rows that carry no brand at all. The brand is checked through a
LEFT JOIN, so a product with no subcategory is judged on its category alone
rather than silently vanishing from the result.

This lives in its own module because more than one layer asks the question — the
checkout guard in :mod:`app.repositories.product` and the popularity rankings in
:mod:`app.repositories.statistics`. Two hand-written copies of the rule would
eventually disagree, and the disagreement would show up as a product a customer
cannot buy sitting in the admin's "worst sellers" list, or worse, the reverse.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, or_

from app.models.category import Category, Subcategory
from app.models.product import Product


def join_product_parents[S: Select[Any]](stmt: S) -> S:
    """
    Join a product's category and — where it has one — its brand.

    The category join is inner: ``category_id`` is ``NOT NULL``, so it never
    drops a row. The brand join is outer, so pre-hierarchy rows survive it.
    """
    return stmt.join(Category, Category.id == Product.category_id).outerjoin(
        Subcategory, Subcategory.id == Product.subcategory_id
    )


def only_sellable_products[S: Select[Any]](stmt: S) -> S:
    """
    Restrict a statement to products a customer could actually buy.

    Adds the parent joins itself, so the caller only needs ``Product`` in scope.
    """
    return join_product_parents(stmt).where(
        Product.is_active.is_(True),
        Category.is_active.is_(True),
        or_(
            Product.subcategory_id.is_(None),
            Subcategory.is_active.is_(True),
        ),
    )
