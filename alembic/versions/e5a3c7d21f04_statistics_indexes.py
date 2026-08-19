"""statistics indexes

Supports the product-popularity aggregate. NON-DESTRUCTIVE: index changes only,
no table, column or row is touched.

``COUNT(DISTINCT order_id) GROUP BY product_id`` over completed orders is the
heaviest query on the dashboard. A composite index on ``(product_id, order_id)``
answers it from the index alone — measured at 60k order items: 204 buffers read
instead of 383, with zero heap fetches.

That composite index also fully serves every ``WHERE product_id = ?`` lookup
(``delete_product``'s reference count) as a leading-column prefix, so the
single-column ``ix_order_items_product_id`` becomes redundant. Verified on a
seeded database: PostgreSQL picked the composite index for that lookup even
while both indexes existed, leaving the single-column one with zero scans.
Dropping it returns the write cost the composite index adds.

Revision ID: e5a3c7d21f04
Revises: d4f2a8c1b9e3
Create Date: 2026-08-19 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5a3c7d21f04"
down_revision: str | None = "d4f2a8c1b9e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create before dropping, so no window exists without an index on product_id.
    op.create_index(
        "ix_order_items_product_id_order_id",
        "order_items",
        ["product_id", "order_id"],
        unique=False,
    )
    op.drop_index("ix_order_items_product_id", table_name="order_items")


def downgrade() -> None:
    op.create_index(
        "ix_order_items_product_id",
        "order_items",
        ["product_id"],
        unique=False,
    )
    op.drop_index("ix_order_items_product_id_order_id", table_name="order_items")
