"""The migration chain builds exactly what the models describe, and can be undone.

The model modules are imported so that their tables are registered on Base.metadata.
"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from ontology_platform import models  # noqa: F401  (registers every module's tables)
from ontology_platform.db import Base
from support import PUBLIC_SEARCH_PATH, alembic_config

SCHEMAS = {table.schema for table in Base.metadata.tables.values()}


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    return type_ != "schema" or name in SCHEMAS


def test_models_cover_identity_and_audit() -> None:
    assert {"identity.users", "identity.sessions", "audit.events"} <= set(Base.metadata.tables)


def test_migrations_match_models(database_url: str) -> None:
    engine = create_engine(database_url, connect_args=PUBLIC_SEARCH_PATH)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"include_schemas": True, "include_name": include_name},
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == []


def test_downgrade_and_upgrade_again(database_url: str) -> None:
    config = alembic_config(database_url)

    command.downgrade(config, "base")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            remaining = set(inspect(connection).get_schema_names()) & {"identity", "audit"}
    finally:
        engine.dispose()
    command.upgrade(config, "head")

    assert remaining == set()
