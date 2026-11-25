"""AI binding suggestion requests (owner: ai module, spec 003 section 8).

Revision ID: 0010
Revises: 0008 (until 0009, the ontology bindings, is written; spec 003 section 16)
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
# TODO(M3 batch 1): becomes "0009" in the commit that adds v0009_ontology_bindings, which waits
# for the alignment PR (#48) to land. Nothing of this branch is merged before then.
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "binding_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("step", sa.String(length=16), nullable=True),
        sa.Column("change_set_id", sa.Uuid(), nullable=True),
        sa.Column("proposed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dropped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("samples_sent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name=op.f("ck_binding_suggestions_status"),
        ),
        sa.CheckConstraint(
            "step IS NULL OR step IN ('catalog', 'match', 'columns', 'changeset')",
            name=op.f("ck_binding_suggestions_step"),
        ),
        sa.CheckConstraint(
            "proposed >= 0 AND dropped >= 0", name=op.f("ck_binding_suggestions_counts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_binding_suggestions")),
        schema="ai",
    )
    op.create_index(
        op.f("ix_binding_suggestions_ontology_id_user_id_created_at"),
        "binding_suggestions",
        ["ontology_id", "user_id", "created_at"],
        schema="ai",
    )


def downgrade() -> None:
    op.drop_table("binding_suggestions", schema="ai")
