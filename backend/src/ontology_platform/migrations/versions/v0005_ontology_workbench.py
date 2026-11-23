"""Ontology workbench: imported IRIs, constraints, axioms, delete and restore (owner: ontology).

Only adds columns and relaxes constraints, so the previous release keeps running on the new
schema (AGENTS.md: 先加后删). See docs/specs/002-m2-ontology-workbench.md, section 3.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ontology"

OLD_KINDS = "'entity_type', 'relation_type', 'property'"
NEW_KINDS = "'entity_type', 'relation_type', 'property', 'constraint', 'axiom'"

OLD_KIND_COLUMNS = (
    "(kind = 'entity_type' AND domain_id IS NULL AND range_id IS NULL"
    " AND datatype IS NULL AND unit IS NULL)"
    " OR (kind = 'relation_type' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NOT NULL AND datatype IS NULL AND unit IS NULL)"
    " OR (kind = 'property' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NULL AND datatype IS NOT NULL)"
)
# Kept in step with models.ELEMENT_KIND_COLUMNS; spelled out so later model changes cannot
# alter what this revision did.
NEW_KIND_COLUMNS = (
    "(kind = 'entity_type' AND domain_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
    " AND datatype IS NULL AND unit IS NULL"
    " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL)"
    " OR (kind = 'relation_type' AND parent_id IS NULL AND datatype IS NULL AND unit IS NULL"
    " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL)"
    " OR (kind = 'property' AND parent_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
    " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL)"
    " OR (kind = 'constraint' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NULL AND inverse_id IS NULL AND datatype IS NULL AND unit IS NULL"
    " AND rules IS NOT NULL AND turtle IS NULL AND subject_id IS NULL)"
    " OR (kind = 'axiom' AND parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL"
    " AND inverse_id IS NULL AND datatype IS NULL AND unit IS NULL AND rules IS NULL"
    " AND turtle IS NOT NULL AND local_name IS NULL AND label_zh IS NULL AND iri IS NULL)"
)
NAMING = (
    "(kind = 'axiom') = (local_name IS NULL)"
    " AND (kind = 'axiom' OR label_zh IS NOT NULL OR iri IS NOT NULL)"
)
OLD_TARGET = (
    "(op = 'create' AND target_element_id IS NULL AND target_revision IS NULL)"
    " OR (op = 'update' AND target_element_id IS NOT NULL AND target_revision IS NOT NULL)"
)
NEW_TARGET = (
    "(op = 'create' AND target_element_id IS NULL AND target_revision IS NULL)"
    " OR (op IN ('update', 'delete', 'restore')"
    " AND target_element_id IS NOT NULL AND target_revision IS NOT NULL)"
)


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check", schema=SCHEMA)
    op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, condition, schema=SCHEMA)


def _jsonb(name: str, default: str | None) -> sa.Column[object]:
    if default is None:
        return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("ontologies", sa.Column("ontology_iri", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("ontologies", _jsonb("prefixes", "{}"), schema=SCHEMA)
    op.add_column("releases", _jsonb("header", None), schema=SCHEMA)

    op.add_column("elements", sa.Column("iri", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("elements", sa.Column("inverse_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(
        "elements",
        sa.Column("auto_shape", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema=SCHEMA,
    )
    op.add_column("elements", _jsonb("rules", None), schema=SCHEMA)
    op.add_column("elements", sa.Column("turtle", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("elements", sa.Column("subject_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column("elements", _jsonb("flags", "[]"), schema=SCHEMA)
    op.alter_column("elements", "local_name", nullable=True, schema=SCHEMA)
    op.alter_column("elements", "label_zh", nullable=True, schema=SCHEMA)
    op.create_foreign_key(
        op.f("fk_elements_inverse_id_elements"),
        "elements",
        "elements",
        ["inverse_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_foreign_key(
        op.f("fk_elements_subject_id_elements"),
        "elements",
        "elements",
        ["subject_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_index(op.f("ix_elements_subject_id"), "elements", ["subject_id"], schema=SCHEMA)
    op.create_unique_constraint(
        op.f("uq_elements_ontology_id_iri"),
        "elements",
        ["ontology_id", "iri"],
        schema=SCHEMA,
    )
    _replace_check("elements", "kind", f"kind IN ({NEW_KINDS})")
    _replace_check("elements", "origin", "origin IN ('ai', 'manual', 'import')")
    _replace_check("elements", "kind_columns", NEW_KIND_COLUMNS)
    op.create_check_constraint(op.f("ck_elements_naming"), "elements", NAMING, schema=SCHEMA)

    _replace_check("change_items", "op", "op IN ('create', 'update', 'delete', 'restore')")
    _replace_check("change_items", "kind", f"kind IN ({NEW_KINDS})")
    _replace_check("change_items", "target", NEW_TARGET)
    _replace_check(
        "change_sets",
        "source",
        "source IN ('ai_extraction', 'ai_assistant', 'manual', 'import')",
    )


def downgrade() -> None:
    # Fails while rows use the new kinds, operations or sources; remove them first.
    _replace_check(
        "change_sets",
        "source",
        "source IN ('ai_extraction', 'ai_assistant', 'manual')",
    )
    _replace_check("change_items", "target", OLD_TARGET)
    _replace_check("change_items", "kind", f"kind IN ({OLD_KINDS})")
    _replace_check("change_items", "op", "op IN ('create', 'update')")

    op.drop_constraint(op.f("ck_elements_naming"), "elements", type_="check", schema=SCHEMA)
    _replace_check("elements", "kind_columns", OLD_KIND_COLUMNS)
    _replace_check("elements", "origin", "origin IN ('ai', 'manual')")
    _replace_check("elements", "kind", f"kind IN ({OLD_KINDS})")
    op.drop_constraint(
        op.f("uq_elements_ontology_id_iri"), "elements", type_="unique", schema=SCHEMA
    )
    op.drop_index(op.f("ix_elements_subject_id"), "elements", schema=SCHEMA)
    op.drop_constraint(
        op.f("fk_elements_subject_id_elements"), "elements", type_="foreignkey", schema=SCHEMA
    )
    op.drop_constraint(
        op.f("fk_elements_inverse_id_elements"), "elements", type_="foreignkey", schema=SCHEMA
    )
    op.alter_column("elements", "label_zh", nullable=False, schema=SCHEMA)
    op.alter_column("elements", "local_name", nullable=False, schema=SCHEMA)
    for column in ("flags", "subject_id", "turtle", "rules", "auto_shape", "inverse_id", "iri"):
        op.drop_column("elements", column, schema=SCHEMA)
    op.drop_column("releases", "header", schema=SCHEMA)
    op.drop_column("ontologies", "prefixes", schema=SCHEMA)
    op.drop_column("ontologies", "ontology_iri", schema=SCHEMA)
