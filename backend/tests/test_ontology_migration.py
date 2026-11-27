"""Revision 0002 builds exactly the ontology tables the models describe, and drops them again."""

from typing import Any
from uuid import uuid4

import psycopg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from httpx import AsyncClient
from sqlalchemy import create_engine, inspect

from ontology_platform import models  # noqa: F401  (registers every module's tables)
from ontology_platform.db import Base
from support import (
    PUBLIC_SEARCH_PATH,
    alembic_config,
    csrf_headers,
    libpq_dsn,
    login,
    truncate_tables,
)

SCHEMA = "ontology"
TABLES = {
    "ontologies",
    "elements",
    "change_sets",
    "change_items",
    "evidence",
    "releases",
    "review_memory",
}


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    return type_ != "schema" or name == SCHEMA


def include_object(
    item: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    table = item if type_ == "table" else getattr(item, "table", None)
    return table is None or table.schema == SCHEMA


def ontology_differences(database_url: str) -> list[Any]:
    engine = create_engine(database_url, connect_args=PUBLIC_SEARCH_PATH)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_schemas": True,
                    "include_name": include_name,
                    "include_object": include_object,
                },
            )
            differences: list[Any] = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    return differences


def ontology_tables(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if SCHEMA not in inspector.get_schema_names():
                return set()
            return set(inspector.get_table_names(schema=SCHEMA))
    finally:
        engine.dispose()


def test_models_register_the_ontology_tables() -> None:
    registered = {table.name for table in Base.metadata.tables.values() if table.schema == SCHEMA}

    assert registered == TABLES


def test_ontology_migration_matches_the_models(database_url: str) -> None:
    assert ontology_tables(database_url) == TABLES
    assert ontology_differences(database_url) == []


def test_ontology_migration_downgrades_completely(database_url: str) -> None:
    # Rows of other tests (with M2 kinds) cannot go back to the M1 constraints.
    truncate_tables(database_url)
    config = alembic_config(database_url)

    command.downgrade(config, "0001")
    try:
        remaining = ontology_tables(database_url)
    finally:
        command.upgrade(config, "head")

    assert remaining == set()
    assert ontology_differences(database_url) == []


async def test_m1_data_still_works_after_the_upgrade(
    client: AsyncClient, database_url: str
) -> None:
    """Spec 002, section 12: on a database with M1 data, the M1 routes keep working."""
    config = alembic_config(database_url)
    command.downgrade(config, "0004")
    ontology, heat, weight, change_set, item, release = (uuid4() for _ in range(6))
    with psycopg.connect(libpq_dsn(database_url), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO ontology.ontologies (id, key, name, base_iri)"
            " VALUES (%s, 'legacy', '旧本体', 'https://example.org/ontology/legacy#')",
            (ontology,),
        )
        conn.execute(
            "INSERT INTO ontology.elements (id, ontology_id, kind, local_name, label_zh, origin)"
            " VALUES (%s, %s, 'entity_type', 'Heat', '炉次', 'ai')",
            (heat, ontology),
        )
        conn.execute(
            "INSERT INTO ontology.elements (id, ontology_id, kind, local_name, label_zh,"
            " domain_id, datatype, required, origin)"
            " VALUES (%s, %s, 'property', 'weight', '重量', %s, 'decimal', true, 'ai')",
            (weight, ontology, heat),
        )
        conn.execute(
            "INSERT INTO ontology.change_sets (id, ontology_id, title, source, status)"
            " VALUES (%s, %s, '识别：旧资料', 'ai_extraction', 'open')",
            (change_set, ontology),
        )
        conn.execute(
            "INSERT INTO ontology.change_items"
            " (id, change_set_id, seq, op, kind, temp_ref, proposed) VALUES"
            " (%s, %s, 1, 'create', 'entity_type', 'new:Slab',"
            ' \'{"localName": "Slab", "labelZh": "板坯"}\')',
            (item, change_set),
        )
        conn.execute(
            "INSERT INTO ontology.releases (id, ontology_id, version, title, snapshot, turtle,"
            " turtle_sha256, element_count) VALUES (%s, %s, 1, '首版', '[]', 'stored turtle',"
            " 'sha', 2)",
            (release, ontology),
        )
        conn.execute(
            "UPDATE ontology.ontologies SET active_release_id = %s WHERE id = %s",
            (release, ontology),
        )
    command.upgrade(config, "head")
    assert (await login(client)).status_code == 200

    listed = (await client.get(f"/api/ontologies/{ontology}/elements")).json()
    exported = await client.get(f"/api/ontologies/{ontology}/export")
    released = await client.get(f"/api/releases/{release}/export")
    decided = await client.post(
        f"/api/change-sets/{change_set}/decisions",
        json={"itemIds": [str(item)], "decision": "accepted"},
        headers=csrf_headers(client),
    )
    merged = await client.post(f"/api/change-sets/{change_set}/merge", headers=csrf_headers(client))
    published = await client.post(
        f"/api/ontologies/{ontology}/releases",
        json={"title": "第二版"},
        headers=csrf_headers(client),
    )

    assert [(e["localName"], e["explicitIri"], e["autoShape"]) for e in listed] == [
        ("Heat", False, True),
        ("weight", False, True),
    ]
    assert listed[0]["iri"] == "https://example.org/ontology/legacy#Heat"
    assert "legacy:Heat-shape" in exported.text
    assert released.text == "stored turtle"
    assert decided.status_code == 200
    assert merged.json() == {"applied": 1, "skipped": []}
    assert published.status_code == 201
