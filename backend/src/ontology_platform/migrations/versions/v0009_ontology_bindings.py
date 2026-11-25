"""Data bindings as elements, catalog evidence, MCP change sets (owner: ontology, spec 003 §6).

Only adds columns (with server defaults where they are not null) and widens constraints, so the
previous release keeps running on the new schema (AGENTS.md: 先加后删). Once binding rows exist,
the previous release cannot list elements any more (it does not know the kinds); spec 003,
section 18 accepts this, as M2 did for constraints and axioms.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ontology"

OLD_KINDS = "'entity_type', 'relation_type', 'property', 'constraint', 'axiom'"
NEW_KINDS = OLD_KINDS + ", 'type_binding', 'property_binding', 'relation_binding'"
BINDING_KINDS = "'type_binding', 'property_binding', 'relation_binding'"
UNNAMED = "'axiom', " + BINDING_KINDS

# Spelled out so that later model changes cannot alter what this revision did; kept in step
# with models.ELEMENT_KIND_COLUMNS and models.ELEMENT_NAMING.
OLD_KIND_COLUMNS = (
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
_BINDING_ONLY = (
    " AND datatype IS NULL AND unit IS NULL AND rules IS NULL AND turtle IS NULL"
    " AND inverse_id IS NULL AND subject_id IS NOT NULL AND binding IS NOT NULL"
    " AND local_name IS NULL AND label_zh IS NULL AND iri IS NULL"
)
NEW_KIND_COLUMNS = (
    "(kind = 'entity_type' AND domain_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
    " AND datatype IS NULL AND unit IS NULL"
    " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL AND binding IS NULL)"
    " OR (kind = 'relation_type' AND parent_id IS NULL AND datatype IS NULL AND unit IS NULL"
    " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL AND binding IS NULL)"
    " OR (kind = 'property' AND parent_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
    " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL AND binding IS NULL)"
    " OR (kind = 'constraint' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NULL AND inverse_id IS NULL AND datatype IS NULL AND unit IS NULL"
    " AND rules IS NOT NULL AND turtle IS NULL AND subject_id IS NULL AND binding IS NULL)"
    " OR (kind = 'axiom' AND parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL"
    " AND inverse_id IS NULL AND datatype IS NULL AND unit IS NULL AND rules IS NULL"
    " AND turtle IS NOT NULL AND local_name IS NULL AND label_zh IS NULL AND iri IS NULL"
    " AND binding IS NULL)"
    " OR (kind = 'type_binding' AND parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL"
    + _BINDING_ONLY
    + ")"
    " OR (kind = 'property_binding' AND parent_id IS NOT NULL AND domain_id IS NULL"
    " AND range_id IS NULL" + _BINDING_ONLY + ")"
    " OR (kind = 'relation_binding' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NOT NULL" + _BINDING_ONLY + ")"
)
OLD_NAMING = (
    "(kind = 'axiom') = (local_name IS NULL)"
    " AND (kind = 'axiom' OR label_zh IS NOT NULL OR iri IS NOT NULL)"
)
NEW_NAMING = (
    f"(kind IN ({UNNAMED})) = (local_name IS NULL)"
    f" AND (kind IN ({UNNAMED}) OR label_zh IS NOT NULL OR iri IS NOT NULL)"
)
OLD_SOURCES = "'ai_extraction', 'ai_assistant', 'manual', 'import'"
NEW_SOURCES = OLD_SOURCES + ", 'ai_binding', 'mcp'"
EVIDENCE_KIND_COLUMNS = (
    "(kind = 'document' AND document_id IS NOT NULL AND chunk_id IS NOT NULL"
    " AND source IS NULL)"
    " OR (kind = 'catalog' AND document_id IS NULL AND chunk_id IS NULL"
    " AND source IS NOT NULL)"
)
ACTIVE_BINDINGS = (
    ("uq_elements_active_type_binding", ["subject_id"], "type_binding"),
    ("uq_elements_active_property_binding", ["parent_id", "subject_id"], "property_binding"),
    (
        "uq_elements_active_relation_binding",
        ["subject_id", "domain_id", "range_id"],
        "relation_binding",
    ),
)


def _replace_check(table: str, name: str, condition: str) -> None:
    constraint = op.f(f"ck_{table}_{name}")
    op.drop_constraint(constraint, table, type_="check", schema=SCHEMA)
    op.create_check_constraint(constraint, table, condition, schema=SCHEMA)


def upgrade() -> None:
    op.add_column(
        "elements",
        sa.Column("binding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )
    _replace_check("elements", "kind", f"kind IN ({NEW_KINDS})")
    _replace_check("elements", "kind_columns", NEW_KIND_COLUMNS)
    _replace_check("elements", "naming", NEW_NAMING)
    for name, columns, kind in ACTIVE_BINDINGS:
        op.create_index(
            name,
            "elements",
            columns,
            unique=True,
            schema=SCHEMA,
            postgresql_where=sa.text(f"kind = '{kind}' AND status = 'active'"),
        )

    _replace_check("change_items", "kind", f"kind IN ({NEW_KINDS})")
    _replace_check("change_sets", "source", f"source IN ({NEW_SOURCES})")
    op.add_column("change_sets", sa.Column("token_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.create_index(op.f("ix_change_sets_token_id"), "change_sets", ["token_id"], schema=SCHEMA)

    # The server default fills existing rows and the previous release's inserts alike.
    op.add_column(
        "evidence",
        sa.Column("kind", sa.String(length=16), server_default="document", nullable=False),
        schema=SCHEMA,
    )
    op.add_column(
        "evidence",
        sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )
    op.alter_column("evidence", "document_id", nullable=True, schema=SCHEMA)
    op.alter_column("evidence", "chunk_id", nullable=True, schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_evidence_kind"), "evidence", "kind IN ('document', 'catalog')", schema=SCHEMA
    )
    op.create_check_constraint(
        op.f("ck_evidence_kind_columns"), "evidence", EVIDENCE_KIND_COLUMNS, schema=SCHEMA
    )

    op.add_column(
        "releases",
        sa.Column("binding_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    # What only this revision can hold goes first: catalog evidence, binding items and
    # elements, and the change sets of the new sources (spec 003, 6.2).
    op.execute("DELETE FROM ontology.evidence WHERE kind = 'catalog'")
    op.execute("DELETE FROM ontology.change_sets WHERE source IN ('ai_binding', 'mcp')")
    op.execute(
        "DELETE FROM ontology.change_items"
        " WHERE kind IN ('type_binding', 'property_binding', 'relation_binding')"
    )
    op.execute(
        "UPDATE ontology.change_items SET applied_element_id = NULL WHERE applied_element_id IN"
        " (SELECT id FROM ontology.elements"
        " WHERE kind IN ('type_binding', 'property_binding', 'relation_binding'))"
    )
    # Property and relation bindings refer to type bindings: delete them first.
    op.execute(
        "DELETE FROM ontology.elements WHERE kind IN ('property_binding', 'relation_binding')"
    )
    op.execute("DELETE FROM ontology.elements WHERE kind = 'type_binding'")

    op.drop_column("releases", "binding_count", schema=SCHEMA)
    op.drop_constraint(op.f("ck_evidence_kind_columns"), "evidence", type_="check", schema=SCHEMA)
    op.drop_constraint(op.f("ck_evidence_kind"), "evidence", type_="check", schema=SCHEMA)
    op.alter_column("evidence", "chunk_id", nullable=False, schema=SCHEMA)
    op.alter_column("evidence", "document_id", nullable=False, schema=SCHEMA)
    op.drop_column("evidence", "source", schema=SCHEMA)
    op.drop_column("evidence", "kind", schema=SCHEMA)

    op.drop_index(op.f("ix_change_sets_token_id"), "change_sets", schema=SCHEMA)
    op.drop_column("change_sets", "token_id", schema=SCHEMA)
    _replace_check("change_sets", "source", f"source IN ({OLD_SOURCES})")
    _replace_check("change_items", "kind", f"kind IN ({OLD_KINDS})")

    for name, _columns, _kind in ACTIVE_BINDINGS:
        op.drop_index(name, "elements", schema=SCHEMA)
    _replace_check("elements", "naming", OLD_NAMING)
    _replace_check("elements", "kind_columns", OLD_KIND_COLUMNS)
    _replace_check("elements", "kind", f"kind IN ({OLD_KINDS})")
    op.drop_column("elements", "binding", schema=SCHEMA)
