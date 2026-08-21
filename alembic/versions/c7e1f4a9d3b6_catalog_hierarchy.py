"""catalog hierarchy: subcategories, localized names, uk locale

Expand-only migration for Category -> Subcategory -> Product.

NON-DESTRUCTIVE BY DESIGN. It adds tables and columns and backfills them from
existing data. It does not drop or rewrite anything:

  * ``categories.name`` is kept and still populated (legacy single-language).
  * ``products.category_id`` is kept and still populated (legacy direct link).

Both are superseded by the new columns but remain so the current handlers keep
working and so this deploy is trivially reversible. A separate CONTRACT
migration removes them once the catalog UI reads the new hierarchy.

Backfill rules:
  * category name_ru/en/de/uk  <- categories.name
  * one subcategory per existing category, named after that category, so every
    product keeps a valid path Category -> Subcategory -> Product
  * products.subcategory_id    <- that category's generated subcategory
  * products.name_uk           <- products.name_ru      (placeholder)
  * products.description_uk    <- products.description_ru (placeholder)

The Ukrainian values are seeded from Russian so the NOT NULL constraints hold
without inventing text. They are placeholders and are expected to be reviewed
in the admin panel.

Revision ID: c7e1f4a9d3b6
Revises: b2c4d5e6f7a8
Create Date: 2026-08-18 14:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7e1f4a9d3b6"
down_revision: str | None = "b2c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- categories
    op.add_column("categories", sa.Column("name_ru", sa.String(255), nullable=True))
    op.add_column("categories", sa.Column("name_en", sa.String(255), nullable=True))
    op.add_column("categories", sa.Column("name_de", sa.String(255), nullable=True))
    op.add_column("categories", sa.Column("name_uk", sa.String(255), nullable=True))
    op.execute(
        "UPDATE categories SET name_ru = name, name_en = name, name_de = name, name_uk = name"
    )
    for column in ("name_ru", "name_en", "name_de", "name_uk"):
        op.alter_column("categories", column, existing_type=sa.String(255), nullable=False)

    op.add_column(
        "categories",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "categories",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "categories",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_categories_is_active", "categories", ["is_active"])

    # -------------------------------------------------------------- subcategories
    op.create_table(
        "subcategories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_de", sa.String(255), nullable=False),
        sa.Column("name_uk", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subcategories_category_id"), "subcategories", ["category_id"])
    op.create_index(
        "ix_subcategories_category_id_is_active",
        "subcategories",
        ["category_id", "is_active"],
    )
    op.create_index("ix_subcategories_sort_order", "subcategories", ["sort_order"])

    # One subcategory per existing category, so no product is left without a path.
    op.execute(
        "INSERT INTO subcategories "
        "(category_id, name_ru, name_en, name_de, name_uk, sort_order, is_active) "
        "SELECT id, name_ru, name_en, name_de, name_uk, 0, true "
        "FROM categories"
    )

    # ------------------------------------------------------------------ products
    op.add_column("products", sa.Column("subcategory_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "products_subcategory_id_fkey",
        "products",
        "subcategories",
        ["subcategory_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "UPDATE products SET subcategory_id = ("
        "  SELECT s.id FROM subcategories s "
        "  WHERE s.category_id = products.category_id "
        "  ORDER BY s.id LIMIT 1)"
    )

    op.add_column("products", sa.Column("name_uk", sa.String(255), nullable=True))
    op.add_column("products", sa.Column("description_uk", sa.Text(), nullable=True))
    op.execute("UPDATE products SET name_uk = name_ru, description_uk = description_ru")
    op.alter_column("products", "name_uk", existing_type=sa.String(255), nullable=False)
    op.alter_column("products", "description_uk", existing_type=sa.Text(), nullable=False)

    op.add_column(
        "products",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(op.f("ix_products_subcategory_id"), "products", ["subcategory_id"])
    op.create_index(
        "ix_products_subcategory_id_is_active",
        "products",
        ["subcategory_id", "is_active"],
    )
    op.create_index("ix_products_is_active", "products", ["is_active"])


def downgrade() -> None:
    # Reverses the expansion. No pre-existing data is lost: `categories.name`
    # and `products.category_id` were never modified by upgrade().
    op.drop_index("ix_products_is_active", table_name="products")
    op.drop_index("ix_products_subcategory_id_is_active", table_name="products")
    op.drop_index(op.f("ix_products_subcategory_id"), table_name="products")
    op.drop_column("products", "updated_at")
    op.drop_column("products", "description_uk")
    op.drop_column("products", "name_uk")
    op.drop_constraint("products_subcategory_id_fkey", "products", type_="foreignkey")
    op.drop_column("products", "subcategory_id")

    op.drop_index("ix_subcategories_sort_order", table_name="subcategories")
    op.drop_index("ix_subcategories_category_id_is_active", table_name="subcategories")
    op.drop_index(op.f("ix_subcategories_category_id"), table_name="subcategories")
    op.drop_table("subcategories")

    op.drop_index("ix_categories_is_active", table_name="categories")
    op.drop_column("categories", "updated_at")
    op.drop_column("categories", "created_at")
    op.drop_column("categories", "is_active")
    op.drop_column("categories", "name_uk")
    op.drop_column("categories", "name_de")
    op.drop_column("categories", "name_en")
    op.drop_column("categories", "name_ru")
