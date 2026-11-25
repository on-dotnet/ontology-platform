"""Alignment records of change items (owner: ontology module, spec 004 sections 5.5 and 9).

Only additions, all nullable: the previous release keeps writing and reading change items.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ontology"
TABLE = "change_items"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("match_kind", sa.String(length=16), nullable=True), schema=SCHEMA
    )
    op.add_column(TABLE, sa.Column("match_element_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("match_item_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("match_reason", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE, sa.Column("match_decision", sa.String(length=16), nullable=True), schema=SCHEMA
    )
    op.create_foreign_key(
        op.f("fk_change_items_match_element_id_elements"),
        TABLE,
        "elements",
        ["match_element_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_foreign_key(
        op.f("fk_change_items_match_item_id_change_items"),
        TABLE,
        TABLE,
        ["match_item_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_change_items_match_item_id"), TABLE, ["match_item_id"], schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_change_items_match_kind"),
        TABLE,
        "match_kind IS NULL OR match_kind IN ('same', 'possible')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_change_items_match_decision"),
        TABLE,
        "match_decision IS NULL OR match_decision IN ('same', 'different')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_change_items_match_decision"), TABLE, type_="check", schema=SCHEMA)
    op.drop_constraint(op.f("ck_change_items_match_kind"), TABLE, type_="check", schema=SCHEMA)
    op.drop_index(op.f("ix_change_items_match_item_id"), TABLE, schema=SCHEMA)
    op.drop_constraint(
        op.f("fk_change_items_match_item_id_change_items"),
        TABLE,
        type_="foreignkey",
        schema=SCHEMA,
    )
    op.drop_constraint(
        op.f("fk_change_items_match_element_id_elements"),
        TABLE,
        type_="foreignkey",
        schema=SCHEMA,
    )
    for column in (
        "match_decision",
        "match_reason",
        "match_item_id",
        "match_element_id",
        "match_kind",
    ):
        op.drop_column(TABLE, column, schema=SCHEMA)
