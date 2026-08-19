"""order payment method

Adds ``orders.payment_method``.

NON-DESTRUCTIVE. A single nullable column, no backfill.

The column is deliberately NULLABLE rather than NOT NULL with a default:
existing orders were placed before the question was asked, so we genuinely do
not know how those customers intended to pay. Writing 'cash' into them would
invent data about real transactions; NULL states the truth, and the UI renders
it as "not specified".

Revision ID: d4f2a8c1b9e3
Revises: c7e1f4a9d3b6
Create Date: 2026-08-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4f2a8c1b9e3"
down_revision: str | None = "c7e1f4a9d3b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "payment_method",
            sa.Enum(
                "cash",
                "card",
                name="payment_method",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_method")
