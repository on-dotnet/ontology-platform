"""Data sources and their cached catalog (owner: connectors module, spec 003 section 5).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateSchema, DropSchema

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.execute(CreateSchema("connectors"))
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("ssl_mode", sa.String(length=16), server_default="prefer", nullable=False),
        sa.Column("schemas", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("secret", sa.LargeBinary(), nullable=True),
        sa.Column("secret_key_id", sa.String(length=16), nullable=True),
        sa.Column("credential_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allow_samples", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_code", sa.String(length=64), nullable=True),
        sa.Column(
            "last_test_warnings", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("catalog_status", sa.String(length=16), server_default="never", nullable=False),
        sa.Column("catalog_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("catalog_error_code", sa.String(length=64), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('postgresql')", name=op.f("ck_data_sources_kind")),
        sa.CheckConstraint(
            "ssl_mode IN ('disable', 'prefer', 'require', 'verify-full')",
            name=op.f("ck_data_sources_ssl_mode"),
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name=op.f("ck_data_sources_status")),
        sa.CheckConstraint(
            "catalog_status IN ('never', 'refreshing', 'ready', 'failed')",
            name=op.f("ck_data_sources_catalog_status"),
        ),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name=op.f("ck_data_sources_port")),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_data_sources_revision")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_sources")),
        sa.UniqueConstraint("name", name=op.f("uq_data_sources_name")),
        schema="connectors",
    )
    op.create_table(
        "catalog_tables",
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("columns", _jsonb(), nullable=False),
        sa.Column("primary_key", _jsonb(), nullable=True),
        sa.Column("foreign_keys", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('table', 'view', 'materialized_view', 'foreign_table')",
            name=op.f("ck_catalog_tables_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["connectors.data_sources.id"],
            name=op.f("fk_catalog_tables_data_source_id_data_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "data_source_id", "schema_name", "table_name", name=op.f("pk_catalog_tables")
        ),
        schema="connectors",
    )


def downgrade() -> None:
    op.drop_table("catalog_tables", schema="connectors")
    op.drop_table("data_sources", schema="connectors")
    op.execute(DropSchema("connectors"))
