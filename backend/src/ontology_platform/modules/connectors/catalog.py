"""Catalog discovery with SQLAlchemy's Inspector (spec 003, 5.5).

`inspect_catalog` runs on a connection that `connection.read_catalog` has already opened read-only
and checked (not the platform's database); it only reads the database's metadata.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import Connection, inspect, text
from sqlalchemy.engine.reflection import ObjectKind

from ontology_platform.modules.connectors import schemas
from ontology_platform.modules.connectors.errors import CatalogTooLargeError
from ontology_platform.modules.connectors.models import ColumnFamily, TableKind

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


_KINDS: dict[str, TableKind] = {
    "r": "table",
    "p": "table",
    "v": "view",
    "m": "materialized_view",
    "f": "foreign_table",
}

_FAMILIES: dict[str, ColumnFamily] = {
    "bpchar": "string",
    "varchar": "string",
    "text": "string",
    "uuid": "opaque",
    "int2": "integer",
    "int4": "integer",
    "int8": "integer",
    "numeric": "decimal",
    "float4": "decimal",
    "float8": "decimal",
    "bool": "boolean",
    "date": "date",
    "timestamp": "dateTime",
    "timestamptz": "dateTime",
}

# Inspector groups some PostgreSQL relation kinds together. Fetch the actual kind and
# comment in the same bounded query, including for relations with no columns.
_RELATIONS = text("""
    SELECT n.nspname, c.relname, c.relkind, pg_catalog.obj_description(c.oid, 'pg_class')
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE (:all_schemas OR n.nspname = ANY(CAST(:schemas AS text[])))
      AND n.nspname <> ALL(CAST(:system_schemas AS text[]))
      AND NOT pg_catalog.starts_with(n.nspname, 'pg_temp_')
      AND NOT pg_catalog.starts_with(n.nspname, 'pg_toast_temp_')
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND c.relpersistence <> 't'
    LIMIT :row_limit
""")

# Reflected SQLAlchemy types lose PostgreSQL's spelling and typmod. Reading pg_attribute
# also avoids trying to construct a dialect type for every user-defined type in the source.
_COLUMNS = text("""
    SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod) AS type_name,
           t.typtype, t.typname, tn.nspname AS type_schema,
           NOT (a.attnotnull OR t.typnotnull) AS nullable,
           pg_catalog.col_description(c.oid, a.attnum) AS comment
    FROM pg_catalog.pg_attribute AS a
    JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_type AS t ON t.oid = a.atttypid
    JOIN pg_catalog.pg_namespace AS tn ON tn.oid = t.typnamespace
    WHERE n.nspname = :schema AND c.relname = ANY(CAST(:names AS text[]))
      AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY c.relname, a.attnum
    LIMIT :row_limit
""")

# Inspector parses the constraint's SQL and can substitute the source schema for public.
# Join both sets of attribute numbers by position to preserve the exact identifiers.
_FOREIGN_KEYS = text("""
    SELECT src.relname, fk.conname, dst_ns.nspname AS ref_schema, dst.relname AS ref_table,
           pg_catalog.array_agg(CAST(src_col.attname AS text) ORDER BY pair.pos) AS source_columns,
           pg_catalog.array_agg(CAST(dst_col.attname AS text) ORDER BY pair.pos) AS ref_columns
    FROM pg_catalog.pg_constraint AS fk
    JOIN pg_catalog.pg_class AS src ON src.oid = fk.conrelid
    JOIN pg_catalog.pg_namespace AS src_ns ON src_ns.oid = src.relnamespace
    JOIN pg_catalog.pg_class AS dst ON dst.oid = fk.confrelid
    JOIN pg_catalog.pg_namespace AS dst_ns ON dst_ns.oid = dst.relnamespace
    CROSS JOIN LATERAL ROWS FROM (
        pg_catalog.unnest(fk.conkey), pg_catalog.unnest(fk.confkey)
    ) WITH ORDINALITY AS pair(src_num, dst_num, pos)
    JOIN pg_catalog.pg_attribute AS src_col
        ON src_col.attrelid = src.oid AND src_col.attnum = pair.src_num
    JOIN pg_catalog.pg_attribute AS dst_col
        ON dst_col.attrelid = dst.oid AND dst_col.attnum = pair.dst_num
    WHERE fk.contype = 'f' AND src_ns.nspname = :schema
      AND src.relname = ANY(CAST(:names AS text[]))
      -- A reference to a partitioned target has internal constraints for its partitions.
      AND NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_constraint AS parent
          WHERE parent.oid = fk.conparentid AND parent.conrelid = fk.conrelid
            AND parent.confrelid <> fk.confrelid
      )
    GROUP BY src.relname, fk.oid, fk.conname, dst_ns.nspname, dst.relname
    ORDER BY src.relname, fk.conname
""")


def _foreign_keys(
    connection: Connection, schema: str, names: list[str]
) -> dict[str, list[schemas.CatalogForeignKey]]:
    result: defaultdict[str, list[schemas.CatalogForeignKey]] = defaultdict(list)
    for row in connection.execute(_FOREIGN_KEYS, {"schema": schema, "names": names}):
        result[row.relname].append(
            schemas.CatalogForeignKey(
                name=row.conname,
                columns=row.source_columns,
                ref_schema=row.ref_schema,
                ref_table=row.ref_table,
                ref_columns=row.ref_columns,
            )
        )
    return result


def _columns(
    connection: Connection, schema: str, names: list[str], remaining: int
) -> dict[str, list[schemas.CatalogColumn]]:
    result: defaultdict[str, list[schemas.CatalogColumn]] = defaultdict(list)
    rows = connection.execute(
        _COLUMNS, {"schema": schema, "names": names, "row_limit": remaining + 1}
    )
    for index, row in enumerate(rows):
        if index == remaining:
            raise CatalogTooLargeError
        family: ColumnFamily = "other"
        if row.typtype == "e":
            family = "opaque"
        elif row.type_schema == "pg_catalog":
            family = _FAMILIES.get(row.typname, "other")
        columns = result[row.relname]
        columns.append(
            schemas.CatalogColumn(
                name=row.attname,
                type=row.type_name,
                family=family,
                nullable=row.nullable,
                comment=row.comment,
                position=len(columns) + 1,
            )
        )
    return result


def inspect_catalog(connection: Connection, schema_names: tuple[str, ...]) -> list[DiscoveredTable]:
    """Every table and view of the given schemas (all non-system schemas when empty), ordered by
    schema and name. Raises CatalogTooLargeError past MAX_TABLES tables or MAX_COLUMNS columns.

    Called through `AsyncConnection.run_sync`, so `connection` is a synchronous one.
    """
    inspector = inspect(connection)
    relations: defaultdict[str, dict[str, tuple[TableKind, str | None]]] = defaultdict(dict)
    rows = connection.execute(
        _RELATIONS,
        {
            "all_schemas": not schema_names,
            "schemas": list(schema_names),
            "system_schemas": list(SYSTEM_SCHEMAS),
            "row_limit": MAX_TABLES + 1,
        },
    )
    for index, (schema, name, relkind, comment) in enumerate(rows):
        if index == MAX_TABLES:
            raise CatalogTooLargeError
        relations[schema][name] = (_KINDS[relkind], comment)

    discovered = []
    remaining = MAX_COLUMNS
    for schema in sorted(relations):
        tables = relations[schema]
        names = sorted(tables)
        columns = _columns(connection, schema, names, remaining)
        remaining -= sum(map(len, columns.values()))
        primary_keys = inspector.get_multi_pk_constraint(
            schema=schema, filter_names=names, kind=ObjectKind.ANY
        )
        foreign_keys = _foreign_keys(connection, schema, names)
        for name in names:
            key = (schema, name)
            pk = primary_keys.get(key)
            pk_columns = pk["constrained_columns"] if pk else []
            kind, comment = tables[name]
            discovered.append(
                DiscoveredTable(
                    schema=schema,
                    name=name,
                    kind=kind,
                    comment=comment,
                    columns=tuple(columns.get(name, [])),
                    primary_key=tuple(pk_columns) if pk_columns else None,
                    foreign_keys=tuple(foreign_keys.get(name, [])),
                )
            )
    return discovered
