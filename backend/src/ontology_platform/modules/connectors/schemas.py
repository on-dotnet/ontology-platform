"""API models of the connectors module (spec 003 appendix), and the frozen copies other modules
receive.

A password only ever travels inwards: it is a `SecretStr` on the way in and no response model
has a field for it.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, SecretStr, StringConstraints

from ontology_platform.modules.connectors.models import (
    IDENTIFIER_MAX_LENGTH,
    NAME_MAX_LENGTH,
    CatalogStatus,
    ColumnFamily,
    DataSourceKind,
    DataSourceStatus,
    SslMode,
    TableKind,
)
from ontology_platform.schemas import CamelModel

SCHEMAS_MAX = 50
PASSWORD_MAX_LENGTH = 1024
TestWarning = Literal["account_can_write"]

Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH),
]
Host = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=IDENTIFIER_MAX_LENGTH)]
Port = Annotated[int, Field(ge=1, le=65535)]
Password = Annotated[SecretStr, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]
SchemaList = Annotated[list[Identifier], Field(max_length=SCHEMAS_MAX)]


class Connection(CamelModel):
    host: str
    port: int
    database: str
    username: str
    ssl_mode: SslMode
    schemas: list[str]


class LastTest(CamelModel):
    at: datetime
    ok: bool
    code: str | None
    warnings: list[TestWarning]


class CatalogInfo(CamelModel):
    status: CatalogStatus
    refreshed_at: datetime | None
    error_code: str | None
    table_count: int


class DataSource(CamelModel):
    id: UUID
    name: str
    kind: DataSourceKind
    status: DataSourceStatus
    # Null for viewers: host, database and user name are for editors and above.
    connection: Connection | None
    has_credential: bool
    credential_updated_at: datetime | None
    allow_samples: bool
    last_test: LastTest | None
    # Null for viewers.
    catalog: CatalogInfo | None
    # Object types of working versions bound to this data source; null when unknown.
    bound_type_count: int | None
    revision: int
    created_at: datetime
    updated_at: datetime


class DataSourceCreate(CamelModel):
    name: Name
    kind: DataSourceKind
    host: Host
    port: Port
    database: Identifier
    username: Identifier
    password: Password
    ssl_mode: SslMode = "prefer"
    schemas: SchemaList = Field(default_factory=list)
    allow_samples: bool = False


class DataSourcePatch(CamelModel):
    """Only the given fields change; leaving out `password` keeps the stored one."""

    name: Name | None = None
    host: Host | None = None
    port: Port | None = None
    database: Identifier | None = None
    username: Identifier | None = None
    password: Password | None = None
    ssl_mode: SslMode | None = None
    schemas: SchemaList | None = None
    allow_samples: bool | None = None
    revision: int = Field(ge=1)


class ConnectionTestRequest(CamelModel):
    """Connection settings that are not saved yet. While editing, leave out `password` and give
    `dataSourceId` to test with the stored one."""

    kind: DataSourceKind
    host: Host
    port: Port
    database: Identifier
    username: Identifier
    password: Password | None = None
    data_source_id: UUID | None = None
    ssl_mode: SslMode = "prefer"
    schemas: SchemaList = Field(default_factory=list)


class ConnectionTest(CamelModel):
    ok: bool
    code: str | None
    # Why the connection failed, when `code` is `datasource.connect_failed`.
    reason: Literal["unreachable", "auth_failed", "database_missing", "ssl", "timeout"] | None
    warnings: list[TestWarning]
    server_version: str | None
    schemas: list[str] | None


class CatalogColumn(CamelModel):
    # Frozen: also part of the copies other modules receive.
    model_config = ConfigDict(frozen=True)

    name: str
    # The type as the data source names it, e.g. "character varying(20)".
    type: str
    family: ColumnFamily
    nullable: bool
    comment: str | None
    position: int


class CatalogForeignKey(CamelModel):
    model_config = ConfigDict(frozen=True)

    name: str | None
    columns: list[str]
    ref_schema: str
    ref_table: str
    ref_columns: list[str]


class BoundTypeRef(CamelModel):
    id: UUID
    label: str


class CatalogTableBrief(CamelModel):
    schema_name: str = Field(alias="schema")
    name: str
    kind: TableKind
    comment: str | None
    column_count: int
    # The object type a working version binds to this table.
    bound_type: BoundTypeRef | None


class CatalogTable(CatalogTableBrief):
    columns: list[CatalogColumn]
    primary_key: list[str] | None
    foreign_keys: list[CatalogForeignKey]
    refreshed_at: datetime


class CatalogSchema(CamelModel):
    name: str
    table_count: int


class CatalogTablePage(CamelModel):
    items: list[CatalogTableBrief]
    next_cursor: str | None


# ---------- copies for other modules ----------


class DataSourceRef(CamelModel):
    """What other modules may know about a data source: never where it is or how to sign in."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    kind: DataSourceKind
    status: DataSourceStatus
    allow_samples: bool
    has_credential: bool
    catalog_status: CatalogStatus


class CatalogTableCopy(CamelModel):
    """A cached catalog table for other modules; detached and frozen at the top level."""

    model_config = ConfigDict(frozen=True)

    data_source_id: UUID
    schema_name: str = Field(alias="schema")
    name: str
    kind: TableKind
    comment: str | None
    columns: tuple[CatalogColumn, ...]
    primary_key: tuple[str, ...] | None
    foreign_keys: tuple[CatalogForeignKey, ...]
    refreshed_at: datetime
