"""Ontology working version, change sets and releases (owner: ontology module).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateSchema, DropSchema

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ontology"
KINDS = "'entity_type', 'relation_type', 'property'"


def _created_at() -> sa.Column[datetime]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _updated_at() -> sa.Column[datetime]:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.execute(CreateSchema(SCHEMA))

    op.create_table(
        "ontologies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_iri", sa.String(length=512), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.Column("active_release_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("key ~ '^[a-z][a-z0-9-]{1,62}$'", name=op.f("ck_ontologies_key")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ontologies")),
        sa.UniqueConstraint("key", name=op.f("uq_ontologies_key")),
        schema=SCHEMA,
    )

    op.create_table(
        "elements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("local_name", sa.String(length=128), nullable=False),
        sa.Column("label_zh", sa.String(length=200), nullable=False),
        sa.Column("label_en", sa.String(length=200), nullable=True),
        sa.Column("definition_zh", sa.Text(), nullable=True),
        sa.Column("definition_en", sa.Text(), nullable=True),
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("domain_id", sa.Uuid(), nullable=True),
        sa.Column("range_id", sa.Uuid(), nullable=True),
        sa.Column("datatype", sa.String(length=16), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("multiple", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_elements_kind")),
        sa.CheckConstraint(
            "datatype IS NULL OR datatype IN "
            "('string', 'integer', 'decimal', 'boolean', 'date', 'dateTime')",
            name=op.f("ck_elements_datatype"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated')",
            name=op.f("ck_elements_status"),
        ),
        sa.CheckConstraint("origin IN ('ai', 'manual')", name=op.f("ck_elements_origin")),
        sa.CheckConstraint(
            "(kind = 'entity_type' AND domain_id IS NULL AND range_id IS NULL"
            " AND datatype IS NULL AND unit IS NULL)"
            " OR (kind = 'relation_type' AND parent_id IS NULL AND domain_id IS NOT NULL"
            " AND range_id IS NOT NULL AND datatype IS NULL AND unit IS NULL)"
            " OR (kind = 'property' AND parent_id IS NULL AND domain_id IS NOT NULL"
            " AND range_id IS NULL AND datatype IS NOT NULL)",
            name=op.f("ck_elements_kind_columns"),
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_elements_revision")),
        sa.ForeignKeyConstraint(
            ["ontology_id"],
            ["ontology.ontologies.id"],
            name=op.f("fk_elements_ontology_id_ontologies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["ontology.elements.id"],
            name=op.f("fk_elements_parent_id_elements"),
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"],
            ["ontology.elements.id"],
            name=op.f("fk_elements_domain_id_elements"),
        ),
        sa.ForeignKeyConstraint(
            ["range_id"],
            ["ontology.elements.id"],
            name=op.f("fk_elements_range_id_elements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_elements")),
        sa.UniqueConstraint(
            "ontology_id",
            "local_name",
            name=op.f("uq_elements_ontology_id_local_name"),
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "change_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _created_at(),
        sa.Column("merged_by", sa.Uuid(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('ai_extraction', 'ai_assistant', 'manual')",
            name=op.f("ck_change_sets_source"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'merged', 'rejected')",
            name=op.f("ck_change_sets_status"),
        ),
        sa.ForeignKeyConstraint(
            ["ontology_id"],
            ["ontology.ontologies.id"],
            name=op.f("fk_change_sets_ontology_id_ontologies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_sets")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_change_sets_ontology_id"),
        "change_sets",
        ["ontology_id"],
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_change_sets_document_id"),
        "change_sets",
        ["document_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "change_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("change_set_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("op", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target_element_id", sa.Uuid(), nullable=True),
        sa.Column("target_revision", sa.Integer(), nullable=True),
        sa.Column("temp_ref", sa.String(length=128), nullable=True),
        sa.Column("proposed", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("edited", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("confidence", sa.Double(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("applied_element_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("op IN ('create', 'update')", name=op.f("ck_change_items_op")),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_change_items_kind")),
        sa.CheckConstraint(
            "decision IN ('pending', 'accepted', 'rejected')",
            name=op.f("ck_change_items_decision"),
        ),
        sa.CheckConstraint(
            "(op = 'create' AND target_element_id IS NULL AND target_revision IS NULL)"
            " OR (op = 'update' AND target_element_id IS NOT NULL"
            " AND target_revision IS NOT NULL)",
            name=op.f("ck_change_items_target"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_change_items_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["ontology.change_sets.id"],
            name=op.f("fk_change_items_change_set_id_change_sets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_element_id"],
            ["ontology.elements.id"],
            name=op.f("fk_change_items_target_element_id_elements"),
        ),
        sa.ForeignKeyConstraint(
            ["applied_element_id"],
            ["ontology.elements.id"],
            name=op.f("fk_change_items_applied_element_id_elements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_items")),
        sa.UniqueConstraint(
            "change_set_id",
            "seq",
            name=op.f("uq_change_items_change_set_id_seq"),
        ),
        sa.UniqueConstraint(
            "change_set_id",
            "temp_ref",
            name=op.f("uq_change_items_change_set_id_temp_ref"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_change_items_target_element_id"),
        "change_items",
        ["target_element_id"],
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_change_items_applied_element_id"),
        "change_items",
        ["applied_element_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("change_item_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("quote", sa.String(length=500), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(char_start IS NULL AND char_end IS NULL)"
            " OR (char_start >= 0 AND char_end >= char_start)",
            name=op.f("ck_evidence_char_range"),
        ),
        sa.ForeignKeyConstraint(
            ["change_item_id"],
            ["ontology.change_items.id"],
            name=op.f("fk_evidence_change_item_id_change_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_evidence_change_item_id"),
        "evidence",
        ["change_item_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "releases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("turtle", sa.Text(), nullable=False),
        sa.Column("turtle_sha256", sa.String(length=64), nullable=False),
        sa.Column("element_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _created_at(),
        sa.CheckConstraint("version >= 1", name=op.f("ck_releases_version")),
        sa.CheckConstraint("element_count >= 0", name=op.f("ck_releases_element_count")),
        sa.ForeignKeyConstraint(
            ["ontology_id"],
            ["ontology.ontologies.id"],
            name=op.f("fk_releases_ontology_id_ontologies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_releases")),
        sa.UniqueConstraint(
            "ontology_id",
            "version",
            name=op.f("uq_releases_ontology_id_version"),
        ),
        schema=SCHEMA,
    )

    op.create_foreign_key(
        op.f("fk_ontologies_active_release_id_releases"),
        "ontologies",
        "releases",
        ["active_release_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_ontologies_active_release_id_releases"),
        "ontologies",
        type_="foreignkey",
        schema=SCHEMA,
    )
    op.drop_table("releases", schema=SCHEMA)
    op.drop_table("evidence", schema=SCHEMA)
    op.drop_table("change_items", schema=SCHEMA)
    op.drop_table("change_sets", schema=SCHEMA)
    op.drop_table("elements", schema=SCHEMA)
    op.drop_table("ontologies", schema=SCHEMA)
    op.execute(DropSchema(SCHEMA))
