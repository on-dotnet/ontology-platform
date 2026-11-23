"""Alembic environment.

Migrations run synchronously (psycopg 3 serves both modes). The database URL comes from
`config.attributes["database_url"]` when set programmatically, otherwise from OP_DATABASE_URL.
The model modules are imported so that every table is registered on Base.metadata.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from ontology_platform import models  # noqa: F401  (registers every module's tables)
from ontology_platform.db import Base
from ontology_platform.settings import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
schemas = {table.schema for table in target_metadata.tables.values()}


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    # Autogenerate only looks at this application's schemas.
    return type_ != "schema" or name in schemas


def database_url() -> str:
    url = config.attributes.get("database_url")
    return str(url) if url else Settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            # The default search_path starts with "$user". A role named like one of our schemas
            # (the default role is "ontology") would make that schema the default one, which
            # Alembic then compares as the unnamed schema and where alembic_version could land.
            connection.exec_driver_sql("SET search_path TO public")
            connection.commit()
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_schemas=True,
                include_name=include_name,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
