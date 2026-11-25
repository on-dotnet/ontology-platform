"""Tables of the connectors module (spec 003, section 5).

A data source row never holds a readable password: `secret` is the AES-256-GCM ciphertext of
the credentials and `secret_key_id` names the key that made it.
"""

from datetime import datetime
from typing import Any, Literal, get_args
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base

SCHEMA = "connectors"

DataSourceKind = Literal["postgresql"]
SslMode = Literal["disable", "prefer", "require", "verify-full"]
DataSourceStatus = Literal["active", "archived"]
CatalogStatus = Literal["never", "refreshing", "ready", "failed"]
TableKind = Literal["table", "view", "materialized_view", "foreign_table"]
# How a column may be compared and which property datatypes it can back (spec 003, 5.5).
ColumnFamily = Literal[
    "string", "opaque", "integer", "decimal", "boolean", "date", "dateTime", "other"
]

NAME_MAX_LENGTH = 100
IDENTIFIER_MAX_LENGTH = 128


def _one_of(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint(_one_of("kind", get_args(DataSourceKind)), name="kind"),
        CheckConstraint(_one_of("ssl_mode", get_args(SslMode)), name="ssl_mode"),
        CheckConstraint(_one_of("status", get_args(DataSourceStatus)), name="status"),
        CheckConstraint(_one_of("catalog_status", get_args(CatalogStatus)), name="catalog_status"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port"),
        CheckConstraint("revision >= 1", name="revision"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int]
    database: Mapped[str] = mapped_column(String(IDENTIFIER_MAX_LENGTH))
    username: Mapped[str] = mapped_column(String(IDENTIFIER_MAX_LENGTH))
    ssl_mode: Mapped[str] = mapped_column(String(16), default="prefer", server_default="prefer")
    # Schemas the catalog is limited to; empty means all of them.
    schemas: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    # Ciphertext of the credentials; cleared when the data source is archived.
    secret: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Fingerprint of the derived key that encrypted `secret`, for key rotation.
    secret_key_id: Mapped[str | None] = mapped_column(String(16))
    credential_updated_at: Mapped[datetime | None]
    # Whether AI binding suggestions may read sample values and send them to the model.
    allow_samples: Mapped[bool] = mapped_column(default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    last_test_at: Mapped[datetime | None]
    last_test_ok: Mapped[bool | None]
    last_test_code: Mapped[str | None] = mapped_column(String(64))
    last_test_warnings: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    catalog_status: Mapped[str] = mapped_column(String(16), default="never", server_default="never")
    catalog_refreshed_at: Mapped[datetime | None]
    catalog_error_code: Mapped[str | None] = mapped_column(String(64))
    # Optimistic lock: incremented on every change.
    revision: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CatalogTable(Base):
    """One table or view of a data source, as the last catalog refresh saw it."""

    __tablename__ = "catalog_tables"
    __table_args__ = (
        CheckConstraint(_one_of("kind", get_args(TableKind)), name="kind"),
        {"schema": SCHEMA},
    )

    data_source_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.data_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    schema_name: Mapped[str] = mapped_column(String(IDENTIFIER_MAX_LENGTH), primary_key=True)
    table_name: Mapped[str] = mapped_column(String(IDENTIFIER_MAX_LENGTH), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    comment: Mapped[str | None] = mapped_column(Text)
    # [{"name", "type", "family", "nullable", "comment", "position"}], see schemas.CatalogColumn.
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    primary_key: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    # [{"name", "columns", "refSchema", "refTable", "refColumns"}]
    foreign_keys: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    refreshed_at: Mapped[datetime] = mapped_column(server_default=func.now())
