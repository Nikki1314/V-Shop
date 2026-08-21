"""drop redundant indexes

NON-DESTRUCTIVE: index changes only. No table, column or row is touched.

Two single-column indexes are fully covered by a composite whose leading column
is the same, so they cost write amplification on the two busiest tables and buy
nothing:

* ``ix_orders_status``            -> ``ix_orders_status_created_at (status, created_at)``
* ``ix_products_subcategory_id``  -> ``ix_products_subcategory_id_is_active
                                       (subcategory_id, is_active)``

Verified on a seeded database (720 products, 20k orders, 60k order items) by
dropping each and re-planning every query that used it. PostgreSQL switched to
the composite in all cases, including ``count(*) WHERE status = ?``, which it
answers as an index-only scan.

``orders`` takes a write on every checkout and every status change; ``products``
on every catalog edit. Removing an index that never gets read is the only index
change this application currently justifies.

Revision ID: f6b1d4e8a207
Revises: e5a3c7d21f04
Create Date: 2026-08-20 14:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f6b1d4e8a207"
down_revision: str | None = "e5a3c7d21f04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_products_subcategory_id", table_name="products")


def downgrade() -> None:
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)
    op.create_index("ix_products_subcategory_id", "products", ["subcategory_id"], unique=False)
