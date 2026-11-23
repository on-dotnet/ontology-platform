"""Tables of the ontology module (see docs/specs/001-m1-ai-ingestion.md, section 3.1).

Columns that hold one of a fixed set of values are plain strings guarded by check constraints;
the allowed values are the `Literal` aliases below, which the API models reuse.
"""

from datetime import datetime
from typing import Any, Literal, get_args
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Double,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base

SCHEMA = "ontology"

Kind = Literal["entity_type", "relation_type", "property"]
Datatype = Literal["string", "integer", "decimal", "boolean", "date", "dateTime"]
ElementStatus = Literal["active", "deprecated"]
Origin = Literal["ai", "manual"]
ChangeSetSource = Literal["ai_extraction", "ai_assistant", "manual"]
ChangeSetStatus = Literal["open", "merged", "rejected"]
ChangeOp = Literal["create", "update"]
Decision = Literal["pending", "accepted", "rejected"]
ItemFlag = Literal["evidence_not_found", "possible_duplicate"]

KINDS: tuple[Kind, ...] = get_args(Kind)
DATATYPES: tuple[Datatype, ...] = get_args(Datatype)
ITEM_FLAGS: tuple[ItemFlag, ...] = get_args(ItemFlag)


def _one_of(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


# Which reference columns each kind uses (spec 3.1: "按 kind 检查各列是否允许为空").
ELEMENT_KIND_COLUMNS = (
    "(kind = 'entity_type' AND domain_id IS NULL AND range_id IS NULL"
    " AND datatype IS NULL AND unit IS NULL)"
    " OR (kind = 'relation_type' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NOT NULL AND datatype IS NULL AND unit IS NULL)"
    " OR (kind = 'property' AND parent_id IS NULL AND domain_id IS NOT NULL"
    " AND range_id IS NULL AND datatype IS NOT NULL)"
)
CHANGE_ITEM_TARGET = (
    "(op = 'create' AND target_element_id IS NULL AND target_revision IS NULL)"
    " OR (op = 'update' AND target_element_id IS NOT NULL AND target_revision IS NOT NULL)"
)


class Ontology(Base):
    __tablename__ = "ontologies"
    __table_args__ = (
        CheckConstraint("key ~ '^[a-z][a-z0-9-]{1,62}$'", name="key"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    base_iri: Mapped[str] = mapped_column(String(512))
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Circular with releases.ontology_id, hence created after both tables.
    active_release_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ontology.releases.id", ondelete="SET NULL", use_alter=True),
    )


class Element(Base):
    """One element of an ontology's working version."""

    __tablename__ = "elements"
    __table_args__ = (
        UniqueConstraint("ontology_id", "local_name"),
        CheckConstraint(_one_of("kind", KINDS), name="kind"),
        CheckConstraint("datatype IS NULL OR " + _one_of("datatype", DATATYPES), name="datatype"),
        CheckConstraint(_one_of("status", get_args(ElementStatus)), name="status"),
        CheckConstraint(_one_of("origin", get_args(Origin)), name="origin"),
        CheckConstraint(ELEMENT_KIND_COLUMNS, name="kind_columns"),
        CheckConstraint("revision >= 1", name="revision"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.ontologies.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    local_name: Mapped[str] = mapped_column(String(128))
    label_zh: Mapped[str] = mapped_column(String(200))
    label_en: Mapped[str | None] = mapped_column(String(200))
    definition_zh: Mapped[str | None] = mapped_column(Text)
    definition_en: Mapped[str | None] = mapped_column(Text)
    # [{"lang": "zh", "text": "钢包"}]
    synonyms: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    domain_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    range_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    datatype: Mapped[str | None] = mapped_column(String(16))
    unit: Mapped[str | None] = mapped_column(String(32))
    required: Mapped[bool] = mapped_column(default=False, server_default=false())
    multiple: Mapped[bool] = mapped_column(default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    origin: Mapped[str] = mapped_column(String(16))
    # Optimistic lock: incremented on every change.
    revision: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ChangeSet(Base):
    __tablename__ = "change_sets"
    __table_args__ = (
        CheckConstraint(_one_of("source", get_args(ChangeSetSource)), name="source"),
        CheckConstraint(_one_of("status", get_args(ChangeSetStatus)), name="status"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.ontologies.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(16))
    # documents.documents.id; no foreign key across modules.
    document_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    merged_by: Mapped[UUID | None]
    merged_at: Mapped[datetime | None]


class ChangeItem(Base):
    __tablename__ = "change_items"
    __table_args__ = (
        UniqueConstraint("change_set_id", "seq"),
        UniqueConstraint("change_set_id", "temp_ref"),
        CheckConstraint(_one_of("op", get_args(ChangeOp)), name="op"),
        CheckConstraint(_one_of("kind", KINDS), name="kind"),
        CheckConstraint(_one_of("decision", get_args(Decision)), name="decision"),
        CheckConstraint(CHANGE_ITEM_TARGET, name="target"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    change_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.change_sets.id", ondelete="CASCADE"),
    )
    seq: Mapped[int]
    op: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    target_element_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ontology.elements.id"),
        index=True,
    )
    # The target's revision when the item was proposed; merge skips the item if it moved on.
    target_revision: Mapped[int | None]
    temp_ref: Mapped[str | None] = mapped_column(String(128))
    # ElementFields with camelCase keys; only the keys that were set.
    proposed: Mapped[dict[str, Any]] = mapped_column(JSONB)
    edited: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    confidence: Mapped[float | None] = mapped_column(Double)
    rationale: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    decided_by: Mapped[UUID | None]
    decided_at: Mapped[datetime | None]
    note: Mapped[str | None] = mapped_column(Text)
    applied_element_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ontology.elements.id"),
        index=True,
    )


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "(char_start IS NULL AND char_end IS NULL)"
            " OR (char_start >= 0 AND char_end >= char_start)",
            name="char_range",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    change_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.change_items.id", ondelete="CASCADE"),
        index=True,
    )
    # documents.documents.id and documents.chunks.id; no foreign keys across modules.
    document_id: Mapped[UUID]
    chunk_id: Mapped[UUID]
    quote: Mapped[str] = mapped_column(String(500))
    char_start: Mapped[int | None]
    char_end: Mapped[int | None]


class Release(Base):
    """An immutable published snapshot of the working version."""

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("ontology_id", "version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("element_count >= 0", name="element_count"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.ontologies.id", ondelete="CASCADE"),
    )
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    # The API `Element` objects (camelCase) of every active element at publish time.
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    turtle: Mapped[str] = mapped_column(Text)
    turtle_sha256: Mapped[str] = mapped_column(String(64))
    element_count: Mapped[int]
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
