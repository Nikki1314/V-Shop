"""
Standing guards on the migration chain.

These are static checks on the migration sources, so they run everywhere the
suite runs — the full audit needs a real PostgreSQL (see
``docs/database-schema.md``), but the rules that matter most are the ones a
reviewer could miss and a test can hold permanently:

* an upgrade must never drop a table, a column or a constraint;
* raw SQL in an upgrade must add or amend data, never remove it;
* the chain must stay linear and single-headed;
* a new model must arrive with the migration that creates its table.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

import app.models  # noqa: F401  (populates the metadata)
from app.database.base import Base

VERSIONS = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"

# Operations that destroy schema or data. None of these belong in an upgrade():
# the expand/contract convention is that removal happens in its own later
# migration, deliberately, once nothing reads the old shape any more.
DESTRUCTIVE_OPS = {"drop_table", "drop_column", "drop_constraint"}

DESTRUCTIVE_SQL = re.compile(
    r"\b(DROP\s+(TABLE|COLUMN|SCHEMA|DATABASE|CONSTRAINT)|TRUNCATE|DELETE\s+FROM)\b",
    re.IGNORECASE,
)

# Dropping an index destroys no data and is reversible, so it is allowed — but
# only where someone decided to, not by accident. Each entry is (revision, index)
# with the reason it is here.
ALLOWED_INDEX_DROPS = {
    # superseded by ix_order_items_product_id_order_id, whose leading column
    # serves every lookup this one did
    ("e5a3c7d21f04", "ix_order_items_product_id"),
    # both superseded by a composite that leads with the same column; verified by
    # re-planning every query that used them on a seeded database
    ("f6b1d4e8a207", "ix_orders_status"),
    ("f6b1d4e8a207", "ix_products_subcategory_id"),
}


def migration_files() -> list[pathlib.Path]:
    return sorted(VERSIONS.glob("*.py"))


def parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def assigned_string(tree: ast.Module, name: str) -> str | None:
    for node in tree.body:
        targets = getattr(node, "targets", None) or (
            [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = getattr(node, "value", None)
                if isinstance(value, ast.Constant):
                    return value.value if isinstance(value.value, str) else None
    return None


def op_calls(scope: ast.AST) -> list[tuple[str, ast.Call]]:
    calls = []
    for node in ast.walk(scope):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ):
            calls.append((node.func.attr, node))
    return calls


def first_string_arg(call: ast.Call) -> str:
    if call.args and isinstance(call.args[0], ast.Constant):
        value = call.args[0].value
        if isinstance(value, str):
            return value
    return ""


def test_there_is_at_least_one_migration() -> None:
    assert migration_files(), "no migrations found — is the path right?"


@pytest.mark.parametrize("path", migration_files(), ids=lambda p: p.stem.split("_")[0])
def test_no_upgrade_destroys_schema_or_data(path: pathlib.Path) -> None:
    """
    The rule that protects production: upgrades add, they do not remove.

    A column dropped here takes its data with it, and the deploy that runs it is
    the moment the old rows stop existing.
    """
    upgrade = function(parse(path), "upgrade")
    assert upgrade is not None, f"{path.name} has no upgrade()"

    offenders = [
        f"line {call.lineno}: op.{op}({first_string_arg(call)!r})"
        for op, call in op_calls(upgrade)
        if op in DESTRUCTIVE_OPS
    ]
    assert offenders == [], (
        f"{path.name} destroys schema in upgrade(): {offenders}. "
        "Removal belongs in its own contract migration, once nothing reads the "
        "old shape."
    )


@pytest.mark.parametrize("path", migration_files(), ids=lambda p: p.stem.split("_")[0])
def test_raw_sql_in_an_upgrade_never_removes_data(path: pathlib.Path) -> None:
    """``op.execute`` bypasses every other guard here, so it gets its own."""
    upgrade = function(parse(path), "upgrade")
    assert upgrade is not None

    for op, call in op_calls(upgrade):
        if op != "execute":
            continue
        sql = " ".join(first_string_arg(call).split())
        assert not DESTRUCTIVE_SQL.search(sql), (
            f"{path.name} line {call.lineno}: destructive raw SQL: {sql[:120]}"
        )
        verb = sql.split()[0].upper() if sql else ""
        assert verb in {"INSERT", "UPDATE", "", "ALTER", "CREATE"}, (
            f"{path.name} line {call.lineno}: unexpected statement {verb}: {sql[:120]}"
        )


@pytest.mark.parametrize("path", migration_files(), ids=lambda p: p.stem.split("_")[0])
def test_index_drops_in_an_upgrade_are_deliberate(path: pathlib.Path) -> None:
    """
    Dropping an index loses no data, but it can quietly lose a query plan.

    Allowed, but only for an entry someone added to ALLOWED_INDEX_DROPS with a
    reason — a new one shows up here as a failure rather than in production as
    a slow query.
    """
    tree = parse(path)
    revision = assigned_string(tree, "revision") or path.stem.split("_")[0]
    upgrade = function(tree, "upgrade")
    assert upgrade is not None

    dropped = {first_string_arg(call) for op, call in op_calls(upgrade) if op == "drop_index"}
    undeclared = {name for name in dropped if (revision, name) not in ALLOWED_INDEX_DROPS}
    assert undeclared == set(), (
        f"{path.name} drops {sorted(undeclared)} in upgrade(). If that is "
        "intended, add it to ALLOWED_INDEX_DROPS with the reason."
    )


@pytest.mark.parametrize("path", migration_files(), ids=lambda p: p.stem.split("_")[0])
def test_every_migration_is_reversible(path: pathlib.Path) -> None:
    """A downgrade that is just `pass` is a one-way door with a handle painted on."""
    tree = parse(path)
    downgrade = function(tree, "downgrade")
    assert downgrade is not None, f"{path.name} has no downgrade()"

    body = [node for node in downgrade.body if not isinstance(node, ast.Expr | ast.Pass)]
    has_ops = bool(op_calls(downgrade))
    assert has_ops or body, f"{path.name} has an empty downgrade() — it cannot be rolled back"


def test_the_revision_chain_is_linear_and_single_headed() -> None:
    chain: dict[str, str | None] = {}
    for path in migration_files():
        tree = parse(path)
        revision = assigned_string(tree, "revision")
        assert revision, f"{path.name} declares no revision id"
        assert path.name.startswith(revision), (
            f"{path.name} does not match its revision id {revision!r}"
        )
        chain[revision] = assigned_string(tree, "down_revision")

    parents = [parent for parent in chain.values() if parent is not None]
    assert len(parents) == len(set(parents)), (
        f"a revision is claimed as parent twice — the chain branched: {parents}"
    )

    roots = [rev for rev, parent in chain.items() if parent is None]
    assert len(roots) == 1, f"expected exactly one base revision, found {roots}"

    heads = set(chain) - set(parents)
    assert len(heads) == 1, f"expected a single head, found {sorted(heads)}"

    for revision, parent in chain.items():
        assert parent is None or parent in chain, (
            f"{revision} points at {parent!r}, which is not in the versions directory"
        )

    # walking from the root must reach every revision
    children = {parent: rev for rev, parent in chain.items() if parent is not None}
    walked, current = 1, roots[0]
    while current in children:
        current, walked = children[current], walked + 1
    assert walked == len(chain), f"walked {walked} of {len(chain)} revisions"


def test_every_model_table_is_created_by_a_migration() -> None:
    """
    A model added without a migration works in tests and fails on deploy.

    Tests build their schema with ``create_all``; production only ever sees what
    the migrations create, so the two sets have to agree.
    """
    created: set[str] = set()
    for path in migration_files():
        upgrade = function(parse(path), "upgrade")
        if upgrade is None:
            continue
        created |= {
            first_string_arg(call) for op, call in op_calls(upgrade) if op == "create_table"
        }

    modelled = set(Base.metadata.tables)
    missing = sorted(modelled - created)
    assert not missing, f"these tables exist in the models but no migration creates them: {missing}"
