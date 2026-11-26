"""Tables of the ontology module (docs/specs/001-m1-ai-ingestion.md 3.1, 002-m2 section 3).

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
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base

SCHEMA = "ontology"

# The semantic kinds make up the ontology; the binding kinds (spec 003, 6.2) tie it to data and
# are never exported as OWL.
SemanticKind = Literal["entity_type", "relation_type", "property", "constraint", "axiom"]
BindingKind = Literal["type_binding", "property_binding", "relation_binding"]
Kind = Literal[
    "entity_type",
    "relation_type",
    "property",
    "constraint",
    "axiom",
    "type_binding",
    "property_binding",
    "relation_binding",
    "metric",
]
Datatype = Literal["string", "integer", "decimal", "boolean", "date", "dateTime"]
ElementStatus = Literal["active", "deprecated"]
Origin = Literal["ai", "manual", "import"]
ChangeSetSource = Literal[
    "ai_extraction", "ai_assistant", "manual", "import", "ai_binding", "mcp", "ai_qa"
]
ChangeSetStatus = Literal["open", "merged", "rejected"]
ChangeOp = Literal["create", "update", "delete", "restore"]
Decision = Literal["pending", "accepted", "rejected"]
ItemFlag = Literal["evidence_not_found", "possible_duplicate", "non_standard", "key_unverified"]
# same: the same concept (model); possible: may be (model, or the write-time recheck); name: the
# main name of a pending item (guardrail G1), which a merge follows while the names agree.
MatchKind = Literal["same", "possible", "name"]
MatchDecision = Literal["same", "different"]
# non_standard: an axiom that OWL API (and so Protégé) rewrites when it reads it.
# key_unverified: a proposed binding key without a primary key or unique constraint behind it.
ElementFlag = Literal["non_standard"]

KINDS: tuple[Kind, ...] = get_args(Kind)
SEMANTIC_KINDS: tuple[SemanticKind, ...] = get_args(SemanticKind)
BINDING_KINDS: tuple[BindingKind, ...] = get_args(BindingKind)
# Kinds without a name or IRI of their own.
UNNAMED_KINDS: tuple[Kind, ...] = ("axiom", *BINDING_KINDS)
EvidenceKind = Literal["document", "catalog"]
DATATYPES: tuple[Datatype, ...] = get_args(Datatype)
ITEM_FLAGS: tuple[ItemFlag, ...] = get_args(ItemFlag)
ELEMENT_FLAGS: tuple[ElementFlag, ...] = get_args(ElementFlag)


def _one_of(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


# Which columns each kind uses (spec 001 3.1, relaxed by 002 3.1: OWL allows a relation or
# property without domain, range or datatype, and imported elements may lack a Chinese label).
_BINDING_ONLY = (
    " AND datatype IS NULL AND unit IS NULL AND rules IS NULL AND turtle IS NULL"
    " AND inverse_id IS NULL AND subject_id IS NOT NULL AND binding IS NOT NULL"
    " AND local_name IS NULL AND label_zh IS NULL AND iri IS NULL"
)
_KIND_COLUMNS = {
    "entity_type": (
        "domain_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
        " AND datatype IS NULL AND unit IS NULL"
        " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL"
    ),
    "relation_type": (
        "parent_id IS NULL AND datatype IS NULL AND unit IS NULL"
        " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL"
    ),
    "property": (
        "parent_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
        " AND rules IS NULL AND turtle IS NULL AND subject_id IS NULL"
    ),
    "constraint": (
        "parent_id IS NULL AND domain_id IS NOT NULL AND range_id IS NULL"
        " AND inverse_id IS NULL AND datatype IS NULL AND unit IS NULL"
        " AND rules IS NOT NULL AND turtle IS NULL AND subject_id IS NULL"
    ),
    "axiom": (
        "parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL"
        " AND inverse_id IS NULL AND datatype IS NULL AND unit IS NULL AND rules IS NULL"
        " AND turtle IS NOT NULL AND local_name IS NULL AND label_zh IS NULL AND iri IS NULL"
    ),
    # Bindings (spec 003, 6.2): subject_id is the element bound; a property binding hangs under
    # its type binding (parent_id), a relation binding joins two type bindings (domain, range).
    "type_binding": "parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL" + _BINDING_ONLY,
    "property_binding": (
        "parent_id IS NOT NULL AND domain_id IS NULL AND range_id IS NULL" + _BINDING_ONLY
    ),
    "relation_binding": (
        "parent_id IS NULL AND domain_id IS NOT NULL AND range_id IS NOT NULL" + _BINDING_ONLY
    ),
    "metric": (
        "parent_id IS NULL AND domain_id IS NULL AND range_id IS NULL AND inverse_id IS NULL"
        " AND datatype IS NULL AND rules IS NULL AND turtle IS NULL AND subject_id IS NOT NULL"
    ),
}
ELEMENT_KIND_COLUMNS = " OR ".join(
    f"(kind = '{kind}' AND {columns}"
    + ("" if kind in BINDING_KINDS else " AND binding IS NULL")
    + (" AND metric IS NOT NULL" if kind == "metric" else " AND metric IS NULL")
    + ")"
    for kind, columns in _KIND_COLUMNS.items()
)
# Elements created in the platform need a Chinese label; imported ones (explicit IRI) may not.
_UNNAMED = _one_of("kind", UNNAMED_KINDS)
ELEMENT_NAMING = (
    f"({_UNNAMED}) = (local_name IS NULL)"
    f" AND ({_UNNAMED} OR label_zh IS NOT NULL OR iri IS NOT NULL)"
)
CHANGE_ITEM_TARGET = (
    "(op = 'create' AND target_element_id IS NULL AND target_revision IS NULL)"
    " OR (op IN ('update', 'delete', 'restore')"
    " AND target_element_id IS NOT NULL AND target_revision IS NOT NULL)"
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
    # IRI of the owl:Ontology; None means base_iri without its trailing # or /.
    ontology_iri: Mapped[str | None] = mapped_column(Text)
    # Prefixes brought by imported files ({"ex": "urn:example:"}); kept for later exports.
    prefixes: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
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
        UniqueConstraint("ontology_id", "iri"),
        CheckConstraint(_one_of("kind", KINDS), name="kind"),
        CheckConstraint("datatype IS NULL OR " + _one_of("datatype", DATATYPES), name="datatype"),
        CheckConstraint(_one_of("status", get_args(ElementStatus)), name="status"),
        CheckConstraint(_one_of("origin", get_args(Origin)), name="origin"),
        CheckConstraint(ELEMENT_KIND_COLUMNS, name="kind_columns"),
        CheckConstraint(ELEMENT_NAMING, name="naming"),
        CheckConstraint("revision >= 1", name="revision"),
        # One active binding per bound thing (spec 003, 6.2).
        Index(
            "uq_elements_active_type_binding",
            "subject_id",
            unique=True,
            postgresql_where=text("kind = 'type_binding' AND status = 'active'"),
        ),
        Index(
            "uq_elements_active_property_binding",
            "parent_id",
            "subject_id",
            unique=True,
            postgresql_where=text("kind = 'property_binding' AND status = 'active'"),
        ),
        Index(
            "uq_elements_active_relation_binding",
            "subject_id",
            "domain_id",
            "range_id",
            unique=True,
            postgresql_where=text("kind = 'relation_binding' AND status = 'active'"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.ontologies.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    # None only for axioms, which have no IRI of their own.
    local_name: Mapped[str | None] = mapped_column(String(128))
    # An IRI brought by an import; None means base_iri + local_name.
    iri: Mapped[str | None] = mapped_column(Text)
    label_zh: Mapped[str | None] = mapped_column(String(200))
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
    # Relations and properties: the object type they belong to. Constraints: the target type.
    domain_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    range_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    inverse_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    datatype: Mapped[str | None] = mapped_column(String(16))
    unit: Mapped[str | None] = mapped_column(String(32))
    required: Mapped[bool] = mapped_column(default=False, server_default=false())
    multiple: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Whether the element takes part in the platform's generated SHACL shape ({type}-shape):
    # always for elements made in the platform, only when the imported file had it otherwise.
    auto_shape: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Constraints: the sh:property rules (camelCase JSON, see schemas.ConstraintRule).
    rules: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    # Axioms: the Turtle fragment, written with the ontology's prefixes and no prefix lines.
    turtle: Mapped[str | None] = mapped_column(Text)
    # Axioms: the element the fragment is about, when its subject is one.
    subject_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ontology.elements.id"),
        index=True,
    )
    flags: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    # Bindings: where the bound element lives in a data source (camelCase JSON, see
    # schemas.Binding). None for the semantic kinds.
    binding: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    metric: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
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
    # identity.access_tokens.id when proposed over MCP; no foreign key across modules.
    token_id: Mapped[UUID | None] = mapped_column(index=True)
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
        CheckConstraint(
            "match_kind IS NULL OR match_kind IN ('same', 'possible', 'name')", name="match_kind"
        ),
        CheckConstraint(
            "match_decision IS NULL OR match_decision IN ('same', 'different')",
            name="match_decision",
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
    # The alignment record (spec 004, 4.3): what the item was found to be the same as, or
    # possibly the same as: an element, or a create item (of this or another change set).
    match_kind: Mapped[str | None] = mapped_column(String(16))
    match_element_id: Mapped[UUID | None] = mapped_column(ForeignKey("ontology.elements.id"))
    match_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ontology.change_items.id", ondelete="SET NULL"),
        index=True,
    )
    match_reason: Mapped[str | None] = mapped_column(Text)
    # The reviewer's conclusion about the alignment: same (merge) or different (keep apart).
    match_decision: Mapped[str | None] = mapped_column(String(16))


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "(char_start IS NULL AND char_end IS NULL)"
            " OR (char_start >= 0 AND char_end >= char_start)",
            name="char_range",
        ),
        CheckConstraint(_one_of("kind", get_args(EvidenceKind)), name="kind"),
        CheckConstraint(
            "(kind = 'document' AND document_id IS NOT NULL AND chunk_id IS NOT NULL"
            " AND source IS NULL)"
            " OR (kind = 'catalog' AND document_id IS NULL AND chunk_id IS NULL"
            " AND source IS NOT NULL)",
            name="kind_columns",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    change_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.change_items.id", ondelete="CASCADE"),
        index=True,
    )
    # A passage of a document, or a fact of a data source's catalog (spec 003, 6.3).
    kind: Mapped[str] = mapped_column(String(16), default="document", server_default="document")
    # documents.documents.id and documents.chunks.id; no foreign keys across modules.
    document_id: Mapped[UUID | None]
    chunk_id: Mapped[UUID | None]
    # Catalog evidence: {dataSourceId, schema, table, column, fact}.
    source: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
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
    # The ontology IRI and prefixes at publish time; None for releases made before M2.
    header: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    turtle: Mapped[str] = mapped_column(Text)
    turtle_sha256: Mapped[str] = mapped_column(String(64))
    # Semantic elements only; bindings are counted apart (spec 003, 6.4).
    element_count: Mapped[int]
    binding_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
