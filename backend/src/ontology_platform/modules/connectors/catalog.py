"""Catalog discovery with SQLAlchemy's Inspector (spec 003, 5.5).

`inspect_catalog` runs on a connection that `connection.read_catalog` has already opened read-only
and checked (not the platform's database); it only reads the database's metadata.
"""

from dataclasses import dataclass

from sqlalchemy import Connection

from ontology_platform.modules.connectors import schemas
from ontology_platform.modules.connectors.models import TableKind

MAX_TABLES = 5_000
MAX_COLUMNS = 200_000
# Never part of a catalog, whatever the schema scope says.
SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


@dataclass(frozen=True, slots=True)
class DiscoveredTable:
    """One table, view, materialized view or foreign table as the database describes it."""

    schema: str
    name: str
    kind: TableKind
    comment: str | None
    # In column order; `type` as PostgreSQL's format_type() names it, e.g. "character varying(20)",
    # "numeric(10,3)", "timestamp with time zone", "uuid", or an enum's name such as
    # "mes.coil_status"; `family` by the table of spec 003, 5.5.
    columns: tuple[schemas.CatalogColumn, ...]
    # None when the table has no primary key (views never have one).
    primary_key: tuple[str, ...] | None
    foreign_keys: tuple[schemas.CatalogForeignKey, ...]


def inspect_catalog(connection: Connection, schema_names: tuple[str, ...]) -> list[DiscoveredTable]:
    """Every table and view of the given schemas (all non-system schemas when empty), ordered by
    schema and name. Raises CatalogTooLargeError past MAX_TABLES tables or MAX_COLUMNS columns.

    Called through `AsyncConnection.run_sync`, so `connection` is a synchronous one.
    """
    raise NotImplementedError("M3 batch 3: catalog discovery")
