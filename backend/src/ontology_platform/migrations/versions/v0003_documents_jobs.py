"""Documents, chunks and the background job queue (owner: documents and jobs modules).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""

from collections.abc import Sequence

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.schema import CreateSchema

    op.execute(CreateSchema("documents"))
    op.execute(CreateSchema("jobs"))
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress", JSONB(), nullable=False),
        sa.Column("error_code", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("char_count", sa.Integer()),
        sa.Column("change_set_id", sa.Uuid()),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'parsing', 'extracting', 'ready', 'failed')",
            name=op.f("ck_documents_status"),
        ),
        sa.UniqueConstraint("ontology_id", "sha256"),
        schema="documents",
    )
    op.create_index(
        "ix_documents_ontology_id_created_at_id",
        "documents",
        ["ontology_id", "created_at", "id"],
        schema="documents",
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer()),
        sa.Column("heading", sa.Text()),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "seq"),
        schema="documents",
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", timestamp, server_default=sa.func.now(), nullable=False),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", timestamp),
        sa.Column("heartbeat_at", timestamp),
        sa.Column("error_code", sa.Text()),
        sa.Column("error_detail", sa.Text()),
        sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", timestamp),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')", name=op.f("ck_jobs_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts")),
        sa.CheckConstraint("max_attempts > 0", name=op.f("ck_jobs_max_attempts")),
        schema="jobs",
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "run_after", "created_at"], schema="jobs")
    op.create_index("ix_jobs_heartbeat", "jobs", ["status", "heartbeat_at"], schema="jobs")


def downgrade() -> None:
    from alembic import op
    from sqlalchemy.schema import DropSchema

    op.drop_table("jobs", schema="jobs")
    op.drop_table("chunks", schema="documents")
    op.drop_table("documents", schema="documents")
    op.execute(DropSchema("jobs"))
    op.execute(DropSchema("documents"))
