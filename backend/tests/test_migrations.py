"""The migration chain builds exactly what the models describe, and can be undone.

The model modules are imported so that their tables are registered on Base.metadata.
"""

from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from psycopg.types.json import Jsonb
from sqlalchemy import ForeignKey, Uuid, create_engine, insert, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ontology_platform import models
from ontology_platform.db import Base
from support import PUBLIC_SEARCH_PATH, alembic_config, libpq_dsn, truncate_tables

SCHEMAS = {table.schema for table in Base.metadata.tables.values()}


class PreviousBase(DeclarativeBase):
    pass


class PreviousChangeSet(PreviousBase):
    __tablename__ = "change_sets"
    __table_args__ = ({"schema": "ontology"},)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    ontology_id: Mapped[UUID] = mapped_column(Uuid)
    title: Mapped[str]
    source: Mapped[str]


class PreviousChangeItem(PreviousBase):
    __tablename__ = "change_items"
    __table_args__ = ({"schema": "ontology"},)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    change_set_id: Mapped[UUID] = mapped_column(ForeignKey("ontology.change_sets.id"))
    seq: Mapped[int]
    op: Mapped[str]
    kind: Mapped[str]
    proposed: Mapped[dict[str, object]] = mapped_column(JSONB)


def test_review_learning_migration_and_previous_orm(database_url: str) -> None:
    truncate_tables(database_url)
    config = alembic_config(database_url)
    command.downgrade(config, "0012")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert not inspect(connection).has_table("review_memory", schema="ontology")
            assert not inspect(connection).has_table("review_assists", schema="ai")
        command.upgrade(config, "0013")
        with engine.connect() as connection:
            assert inspect(connection).has_table("review_memory", schema="ontology")
            assert inspect(connection).has_table("review_assists", schema="ai")
        with Session(engine) as session:
            ontology_id = uuid4()
            change_set_id = uuid4()
            session.execute(
                insert(models.ontology_models.Ontology).values(
                    id=ontology_id, key="previous", name="Previous", base_iri="urn:previous:"
                )
            )
            session.add(
                PreviousChangeSet(
                    id=change_set_id, ontology_id=ontology_id, title="previous", source="manual"
                )
            )
            session.flush()
            session.add(
                PreviousChangeItem(
                    id=uuid4(),
                    change_set_id=change_set_id,
                    seq=1,
                    op="create",
                    kind="entity_type",
                    proposed={"labelZh": "旧版"},
                )
            )
            session.commit()
            assert session.get(PreviousChangeSet, change_set_id) is not None
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT suppressed, suppressed_total FROM ontology.change_sets WHERE id = %s",
                (change_set_id,),
            ).one() == ([], 0)
        command.downgrade(config, "0012")
        command.upgrade(config, "0013")
    finally:
        engine.dispose()
        command.upgrade(config, "head")


def test_binding_suggestion_dropped_reasons_migration(database_url: str) -> None:
    config = alembic_config(database_url)
    column = (
        "SELECT data_type, is_nullable, column_default FROM information_schema.columns"
        " WHERE table_schema = 'ai' AND table_name = 'binding_suggestions'"
        " AND column_name = 'dropped_reasons'"
    )
    previous_insert = (
        "INSERT INTO ai.binding_suggestions"
        " (id, ontology_id, data_source_id, user_id, scope, status, dropped)"
        " VALUES (%s, gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),"
        " '{}', 'succeeded', 2)"
    )
    existing_id, new_id = uuid4(), uuid4()
    with psycopg.connect(libpq_dsn(database_url), autocommit=True) as conn:
        command.downgrade(config, "0013")
        try:
            conn.execute(previous_insert, (existing_id,))
            command.upgrade(config, "0014")
            assert conn.execute(column).fetchone() == ("jsonb", "YES", None)
            conn.execute(previous_insert, (new_id,))
            assert conn.execute(
                "SELECT count(*) FROM ai.binding_suggestions"
                " WHERE id IN (%s, %s) AND dropped = 2 AND dropped_reasons IS NULL",
                (existing_id, new_id),
            ).fetchone() == (2,)
            command.downgrade(config, "0013")
            assert conn.execute(column).fetchone() is None
        finally:
            command.upgrade(config, "head")


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
    # Rows of other tests (with M2 kinds) cannot go back to the M1 constraints.
    truncate_tables(database_url)
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


def test_m4_downgrade_preserves_legacy_items_and_snapshots(database_url: str) -> None:
    truncate_tables(database_url)
    config = alembic_config(database_url)
    dsn = libpq_dsn(database_url)
    ontology, subject, metric, manual, qa = (uuid4() for _ in range(5))
    survivors = [{"kind": "entity_type", "id": str(subject)}, {"kind": "axiom", "turtle": "x"}]
    metric_entry = {"kind": "metric", "id": str(metric), "metric": {"aggregate": "count"}}
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO ontology.ontologies (id, key, name, base_iri)"
            " VALUES (%s, 'steel', 'Steel', 'urn:steel:')",
            (ontology,),
        )
        conn.execute(
            "INSERT INTO ontology.elements (id, ontology_id, kind, local_name, label_zh, origin)"
            " VALUES (%s, %s, 'entity_type', 'Heat', '炉次', 'manual')",
            (subject, ontology),
        )
        conn.execute(
            "INSERT INTO ontology.elements"
            " (id, ontology_id, kind, local_name, label_zh, origin, subject_id, unit, metric)"
            " VALUES (%s, %s, 'metric', 'heatCount', '炉次数', 'manual', %s, '炉', %s)",
            (metric, ontology, subject, Jsonb(metric_entry["metric"])),
        )
        conn.execute(
            "INSERT INTO ontology.change_sets (id, ontology_id, title, source)"
            " VALUES (%s, %s, 'manual', 'manual'), (%s, %s, 'gap', 'ai_qa')",
            (manual, ontology, qa, ontology),
        )
        conn.execute(
            "INSERT INTO ontology.change_items"
            " (id, change_set_id, seq, op, kind, proposed, applied_element_id) VALUES"
            " (gen_random_uuid(), %s, 1, 'create', 'metric', '{}', %s),"
            " (gen_random_uuid(), %s, 2, 'create', 'property', '{}', %s),"
            " (gen_random_uuid(), %s, 3, 'create', 'entity_type', '{}', %s),"
            " (gen_random_uuid(), %s, 1, 'create', 'property', '{}', NULL)",
            (manual, metric, manual, metric, manual, subject, qa),
        )
        # References to the metric from items of other kinds must not block its removal.
        conn.execute(
            "UPDATE ontology.change_items SET match_kind = 'possible', match_element_id = %s"
            " WHERE seq = 3",
            (metric,),
        )
        conn.execute(
            "INSERT INTO ontology.change_items"
            " (id, change_set_id, seq, op, kind, proposed, target_element_id, target_revision)"
            " VALUES (gen_random_uuid(), %s, 4, 'update', 'property', '{}', %s, 1)",
            (manual, metric),
        )
        mixed = [survivors[0] | {"metric": None}, metric_entry, survivors[1] | {"metric": None}]
        conn.execute(
            "INSERT INTO ontology.releases"
            " (id, ontology_id, version, title, snapshot, turtle, turtle_sha256, element_count)"
            " VALUES (gen_random_uuid(), %s, 1, 'mixed', %s, '', '', 2),"
            " (gen_random_uuid(), %s, 2, 'no metrics', %s, '', '', 1)",
            (ontology, Jsonb(mixed), ontology, Jsonb([survivors[0] | {"metric": None}])),
        )
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="ck_elements_kind_columns"),
            conn.transaction(),
        ):
            conn.execute("UPDATE ontology.elements SET metric = '{}' WHERE id = %s", (subject,))
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="ck_elements_kind_columns"),
            conn.transaction(),
        ):
            conn.execute("UPDATE ontology.elements SET subject_id = NULL WHERE id = %s", (metric,))

    command.downgrade(config, "0011")
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            assert conn.execute("SELECT id FROM ontology.elements").fetchall() == [(subject,)]
            assert conn.execute("SELECT id FROM ontology.change_sets").fetchall() == [(manual,)]
            items = conn.execute(
                "SELECT seq, applied_element_id, match_element_id"
                " FROM ontology.change_items ORDER BY seq"
            )
            assert items.fetchall() == [(2, None, None), (3, subject, None)]
            snapshots = conn.execute("SELECT snapshot FROM ontology.releases ORDER BY version")
            assert snapshots.fetchall() == [(survivors,), ([survivors[0]],)]
            dropped = conn.execute("SELECT to_regclass('ai.qa_questions'), to_regnamespace('cq')")
            assert dropped.fetchone() == (None, None)
            with pytest.raises(psycopg.errors.CheckViolation, match='"ck_elements_kind"'):
                conn.execute(
                    "INSERT INTO ontology.elements"
                    " (id, ontology_id, kind, local_name, label_zh, origin, subject_id)"
                    " VALUES (%s, %s, 'metric', 'heatCount', '炉次数', 'manual', %s)",
                    (metric, ontology, subject),
                )
            with pytest.raises(psycopg.errors.CheckViolation, match="ck_elements_kind_columns"):
                conn.execute("UPDATE ontology.elements SET unit = 'kg' WHERE id = %s", (subject,))
            with pytest.raises(psycopg.errors.CheckViolation, match="ck_change_items_kind"):
                conn.execute("UPDATE ontology.change_items SET kind = 'metric' WHERE seq = 2")
            with pytest.raises(psycopg.errors.CheckViolation, match="ck_change_sets_source"):
                conn.execute("UPDATE ontology.change_sets SET source = 'ai_qa'")
    finally:
        command.upgrade(config, "head")
