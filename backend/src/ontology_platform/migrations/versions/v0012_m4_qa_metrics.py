"""Metrics, QA questions and competency checks (spec 007, section 14).

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema, DropSchema

from ontology_platform.migrations.versions import v0009_ontology_bindings as v0009

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# In the frozen 0009 expression each closing parenthesis ends one kind's branch.
KIND_COLUMNS = v0009.NEW_KIND_COLUMNS.replace(")", " AND metric IS NULL)") + (
    " OR (kind = 'metric' AND parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL"
    " AND inverse_id IS NULL AND datatype IS NULL AND rules IS NULL AND turtle IS NULL"
    " AND subject_id IS NOT NULL AND binding IS NULL AND metric IS NOT NULL)"
)


def _ontology_checks(kinds: str, columns: str, sources: str) -> None:
    for table, name, condition in (
        ("elements", "kind", f"kind IN ({kinds})"),
        ("elements", "kind_columns", columns),
        ("change_items", "kind", f"kind IN ({kinds})"),
        ("change_sets", "source", f"source IN ({sources})"),
    ):
        constraint = op.f(f"ck_{table}_{name}")
        op.drop_constraint(constraint, table, type_="check", schema="ontology")
        op.create_check_constraint(constraint, table, condition, schema="ontology")


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _create_qa_questions() -> None:
    op.create_table(
        "qa_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("cq_question_id", sa.Uuid()),
        sa.Column("asked_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("step", sa.String(16)),
        sa.Column("release_id", sa.Uuid()),
        sa.Column("release_version", sa.Integer()),
        sa.Column("plan", JSONB()),
        sa.Column("gaps", JSONB()),
        sa.Column("answer", JSONB()),
        sa.Column("evidence", JSONB()),
        sa.Column("answer_keys", JSONB()),
        sa.Column("gap_status", sa.String(16)),
        sa.Column("gap_change_set_id", sa.Uuid()),
        sa.Column("gap_dropped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gap_error_code", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        _timestamp("created_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("char_length(question) BETWEEN 1 AND 500", name="question"),
        sa.CheckConstraint("origin IN ('user', 'cq')", name="origin"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'answered', 'unanswerable', 'failed')", name="status"
        ),
        sa.CheckConstraint(
            "step IS NULL OR step IN ('plan', 'check', 'query', 'answer', 'done')", name="step"
        ),
        sa.CheckConstraint(
            "gap_status IS NULL OR gap_status IN ('queued', 'running', 'done', 'empty', 'failed')",
            name="gap_status",
        ),
        sa.CheckConstraint("gap_dropped >= 0", name="gap_dropped"),
        schema="ai",
    )
    for column in ("asked_by", "ontology_id"):
        op.create_index(
            op.f(f"ix_qa_questions_{column}_created_at"),
            "qa_questions",
            [column, "created_at"],
            schema="ai",
        )


def _create_cq() -> None:
    op.execute(CreateSchema("cq"))
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ontology_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("expect_kind", sa.String(16), nullable=False),
        sa.Column("expect_objects", JSONB()),
        sa.Column("expect_number", sa.Numeric()),
        sa.Column("tolerance", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(1000)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "expect_kind IN ('answerable', 'objects', 'number')", name="expect_kind"
        ),
        schema="cq",
    )
    op.create_table(
        "checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("question_id", sa.Uuid(), sa.ForeignKey("cq.questions.id"), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("qa_question_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("detail", JSONB()),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _timestamp("created_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "result IN ('pending', 'pass', 'fail', 'unanswerable', 'error')", name="result"
        ),
        schema="cq",
    )


def upgrade() -> None:
    op.add_column("elements", sa.Column("metric", JSONB()), schema="ontology")
    _ontology_checks(v0009.NEW_KINDS + ", 'metric'", KIND_COLUMNS, v0009.NEW_SOURCES + ", 'ai_qa'")
    _create_qa_questions()
    _create_cq()


def downgrade() -> None:
    op.execute("DELETE FROM ontology.change_sets WHERE source = 'ai_qa'")
    metrics = "(SELECT id FROM ontology.elements WHERE kind = 'metric')"
    op.execute(
        "DELETE FROM ontology.change_items"
        f" WHERE kind = 'metric' OR target_element_id IN {metrics}"
    )
    # No foreign key to a metric may survive, whatever kind the referring item has.
    for column in ("applied_element_id", "match_element_id"):
        op.execute(
            f"UPDATE ontology.change_items SET {column} = NULL WHERE {column} IN {metrics}"
        )
    op.execute("DELETE FROM ontology.elements WHERE kind = 'metric'")
    # Old readers validate every entry, including releases that contained no metrics.
    op.execute(
        """
        UPDATE ontology.releases SET snapshot = (
            SELECT coalesce(jsonb_agg(item - 'metric' ORDER BY pos), '[]'::jsonb)
            FROM jsonb_array_elements(snapshot) WITH ORDINALITY AS entries(item, pos)
            WHERE item->>'kind' IS DISTINCT FROM 'metric'
        )
        WHERE snapshot @? '$[*].metric' OR snapshot @> '[{"kind":"metric"}]'
        """
    )
    _ontology_checks(v0009.NEW_KINDS, v0009.NEW_KIND_COLUMNS, v0009.NEW_SOURCES)
    op.drop_column("elements", "metric", schema="ontology")
    op.drop_table("qa_questions", schema="ai")
    op.drop_table("checks", schema="cq")
    op.drop_table("questions", schema="cq")
    op.execute(DropSchema("cq"))
