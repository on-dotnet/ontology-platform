"""AI run accounting (owner: ai module).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSchema, DropSchema

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(CreateSchema("ai"))
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('succeeded', 'failed')", name=op.f("ck_runs_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        schema="ai",
    )
    op.create_index(op.f("ix_runs_created_at"), "runs", ["created_at"], schema="ai")
    op.create_index(op.f("ix_runs_document_id"), "runs", ["document_id"], schema="ai")


def downgrade() -> None:
    op.drop_table("runs", schema="ai")
    op.execute(DropSchema("ai"))
