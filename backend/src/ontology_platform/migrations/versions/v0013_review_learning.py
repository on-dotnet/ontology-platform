"""Review memory and assistance storage (spec 008).

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("change_items", sa.Column("reject_reason", sa.Text()), schema="ontology")
    op.create_check_constraint(
        op.f("ck_change_items_reject_reason"),
        "change_items",
        "reject_reason IS NULL OR reject_reason IN "
        "('out_of_scope', 'incorrect', 'duplicate', 'keep_open')",
        schema="ontology",
    )
    op.add_column(
        "change_sets",
        sa.Column("suppressed", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="ontology",
    )
    # `suppressed` keeps at most 200 entries; the total counts the rest too.
    op.add_column(
        "change_sets",
        sa.Column("suppressed_total", sa.Integer(), nullable=False, server_default="0"),
        schema="ontology",
    )
    op.create_table(
        "review_memory",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "ontology_id",
            sa.Uuid(),
            sa.ForeignKey("ontology.ontologies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("element_kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "source_change_set_id",
            sa.Uuid(),
            sa.ForeignKey("ontology.change_sets.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_item_id",
            sa.Uuid(),
            sa.ForeignKey("ontology.change_items.id", ondelete="SET NULL"),
        ),
        sa.Column("decided_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_reason", sa.Text()),
        sa.Column("deleted_by", sa.Uuid()),
        sa.CheckConstraint("kind IN ('rejected', 'renamed', 'kept_apart')", name="kind"),
        sa.CheckConstraint(
            "element_kind IN ('entity_type', 'relation_type', 'property')", name="element_kind"
        ),
        sa.CheckConstraint(
            "deleted_reason IS NULL OR deleted_reason IN "
            "('deleted', 'cleared', 'evicted', 'superseded')",
            name="deleted_reason",
        ),
        sa.UniqueConstraint("ontology_id", "kind", "element_kind", "key"),
        schema="ontology",
    )
    op.create_index(
        op.f("ix_review_memory_ontology_id_active"),
        "review_memory",
        ["ontology_id"],
        schema="ontology",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "review_assists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("change_set_id", sa.Uuid(), nullable=False),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid()),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text()),
        sa.Column("ai_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("items_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_ai", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'partial', 'failed')", name="status"
        ),
        schema="ai",
    )
    op.create_index(
        op.f("ix_review_assists_change_set_id_created_at"),
        "review_assists",
        ["change_set_id", sa.text("created_at DESC")],
        schema="ai",
    )
    op.create_index(
        op.f("ix_review_assists_requested_by_created_at"),
        "review_assists",
        ["requested_by", "created_at"],
        schema="ai",
    )
    op.create_index(
        op.f("uq_review_assists_change_set_id_running"),
        "review_assists",
        ["change_set_id"],
        unique=True,
        schema="ai",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_table("review_assists", schema="ai")
    op.drop_table("review_memory", schema="ontology")
    op.drop_column("change_sets", "suppressed_total", schema="ontology")
    op.drop_column("change_sets", "suppressed", schema="ontology")
    op.drop_constraint(
        op.f("ck_change_items_reject_reason"), "change_items", type_="check", schema="ontology"
    )
    op.drop_column("change_items", "reject_reason", schema="ontology")
