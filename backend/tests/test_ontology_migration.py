"""Revision 0002 builds exactly the ontology tables the models describe, and drops them again."""

from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from ontology_platform import models  # noqa: F401  (registers every module's tables)
from ontology_platform.db import Base
from support import PUBLIC_SEARCH_PATH, alembic_config, truncate_tables

SCHEMA = "ontology"
TABLES = {"ontologies", "elements", "change_sets", "change_items", "evidence", "releases"}


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
