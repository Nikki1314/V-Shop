"""performance indexes

Revision ID: b2c4d5e6f7a8
Revises: a9b389353e68
Create Date: 2026-08-03 16:12:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2c4d5e6f7a8"
down_revision: str | None = "a9b389353e68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_products_category_id_is_active",
        "products",
        ["category_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_orders_status_created_at",
        "orders",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_categories_sort_order",
        "categories",
        ["sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_categories_name",
        "categories",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_index("ix_categories_sort_order", table_name="categories")
    op.drop_index("ix_orders_status_created_at", table_name="orders")
    op.drop_index("ix_products_category_id_is_active", table_name="products")
