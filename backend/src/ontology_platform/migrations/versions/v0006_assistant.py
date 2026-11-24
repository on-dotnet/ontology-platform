"""AI assistant requests (owner: ai module, spec 002 section 10).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("step", sa.String(length=16), nullable=True),
        sa.Column("reply", sa.Text(), nullable=True),
        sa.Column("dropped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("change_set_id", sa.Uuid(), nullable=True),
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
            name=op.f("ck_assistant_requests_status"),
        ),
        sa.CheckConstraint(
            "step IS NULL OR step IN ('context', 'model', 'changeset')",
            name=op.f("ck_assistant_requests_step"),
        ),
        sa.CheckConstraint(
            "char_length(message) BETWEEN 1 AND 2000",
            name=op.f("ck_assistant_requests_message"),
        ),
        sa.CheckConstraint("dropped >= 0", name=op.f("ck_assistant_requests_dropped")),
        sa.ForeignKeyConstraint(
            ["ontology_id"],
            ["ontology.ontologies.id"],
            name=op.f("fk_assistant_requests_ontology_id_ontologies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["ontology.change_sets.id"],
            name=op.f("fk_assistant_requests_change_set_id_change_sets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_requests")),
        schema="ai",
    )
    op.create_index(
        op.f("ix_assistant_requests_ontology_id_user_id_created_at"),
        "assistant_requests",
        ["ontology_id", "user_id", "created_at"],
        schema="ai",
    )


def downgrade() -> None:
    op.drop_table("assistant_requests", schema="ai")
