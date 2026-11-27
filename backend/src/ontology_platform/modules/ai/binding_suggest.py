"""AI binding suggestions (spec 003, section 8): the model matches object types to tables,
properties to columns and relations to foreign keys from catalog metadata, deterministic code
checks every match, and what passes becomes a change set for review.

Like every AI proposal, the only output is a change set (source `ai_binding`) whose items all
wait for review: nothing here writes a binding, accepts an item or merges.

This module only takes up the model's answers: the ids, tables and columns it names must be
shown to it, a table's own primary key wins over the model's choice, and the evidence is built
from the catalog cache, not from what the model says. Whether a binding is valid (column types,
keys, references) is decided by the ontology module's binding rules when the change set is
proposed (`ontology.binding_proposals.propose_bindings`); what fails there is dropped too.

The model sees catalog metadata, and sample values only while the data source allows them
(read through `connectors.service.sample_values`, each read audited). Connection parameters
and credentials never reach this module: `DataSourceRef` and `CatalogTableCopy` carry neither.
"""

import json
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import schemas
from ontology_platform.modules.ai.binding_prompts import (
    COLUMNS_INSTRUCTIONS,
    COLUMNS_PURPOSE,
    MATCH_INSTRUCTIONS,
    MATCH_PURPOSE,
    ColumnsOut,
    MatchOut,
    RelationMatchOut,
)
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.models import BindingSuggestion
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.errors import ConnectorError, SourceDisabledError
from ontology_platform.modules.connectors.schemas import CatalogTableCopy, DataSourceRef
from ontology_platform.modules.connectors.statements import TableRef as CatalogRef
from ontology_platform.modules.jobs import service as jobs
from ontology_platform.modules.jobs.runner import JobContext, RetryableJobError
from ontology_platform.modules.ontology import binding_proposals
from ontology_platform.modules.ontology import bindings as ontology_bindings
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.schemas import (
    CatalogEvidenceSource,
    ColumnBinding,
    Element,
    ElementFields,
    EvidenceIn,
    ForeignKeyJoin,
    JoinBinding,
    LinkTableJoin,
    ProposedItem,
    TableBinding,
    TypeBindingView,
)

# Payload: {"suggestionId": "<uuid>"}
JOB_KIND = "bindings.suggest"
TABLES_MAX = 200
COLUMNS_MAX = 4000
DEFINITION_MAX_LENGTH = 200
# Shown to reviewers: short, so that text steered by comments in the catalog cannot pose as a
# review note at length.
RATIONALE_MAX_LENGTH = 300
QUOTE_MAX_LENGTH = 500
# A comment longer than this says nothing more about which column is which.
COMMENT_MAX_LENGTH = 200

type Table = CatalogTableCopy
type TableKey = tuple[str, str]


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found() -> AppError:
    return AppError(404, "binding_suggestion.not_found", "Binding suggestion not found.")


def _out(row: BindingSuggestion) -> schemas.BindingSuggestion:
    return schemas.BindingSuggestion(
        id=row.id,
        ontology_id=row.ontology_id,
        data_source_id=row.data_source_id,
        status=cast(Any, row.status),
        step=cast(Any, row.step),
        change_set_id=row.change_set_id,
        proposed=row.proposed,
        dropped=row.dropped,
        samples_sent=row.samples_sent,
        error_code=row.error_code,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


async def _usable_source(db: AsyncSession, data_source_id: UUID) -> DataSourceRef:
    source = await connectors.get_data_source_ref(db, data_source_id)
    if source is None:
        raise AppError(404, "datasource.not_found", "The data source was not found.")
    if source.status != "active":
        raise AppError(409, "datasource.archived", "The data source is archived.")
    if source.catalog_status == "never":
        raise AppError(409, "catalog.not_ready", "The catalog has not been read yet.")
    return source


async def _scope_tables(
    db: AsyncSession, data_source_id: UUID, scope: dict[str, Any]
) -> tuple[Table, ...]:
    tables = scope.get("tables")
    if tables is not None:
        refs = tuple(CatalogRef(schema=t["schema"], name=t["name"]) for t in tables)
        return await connectors.list_catalog_tables_for(db, data_source_id, tables=refs)
    return await connectors.list_catalog_tables_for(
        db, data_source_id, schema_names=tuple(scope.get("schemas") or ())
    )


def _check_size(tables: Sequence[Table]) -> None:
    columns = sum(len(table.columns) for table in tables)
    if len(tables) > TABLES_MAX or columns > COLUMNS_MAX:
        raise AppError(
            422,
            "binding_suggestion.scope_too_large",
            f"At most {TABLES_MAX} tables and {COLUMNS_MAX} columns at a time.",
        )


async def create_request(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.BindingSuggestionCreate,
    *,
    user_id: UUID,
    ip: str | None,
) -> schemas.BindingSuggestion:
    """Store the request and queue the job that answers it."""
    if not await ontology.ontology_exists(db, ontology_id):
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    source = await _usable_source(db, body.data_source_id)
    scope = body.model_dump(mode="json", by_alias=True, include={"tables", "schemas", "type_ids"})
    tables = await _scope_tables(db, source.id, scope)
    if not tables:
        raise AppError(
            422, "binding_suggestion.scope_empty", "The catalog has no tables in this scope."
        )
    _check_size(tables)
    columns = sum(len(table.columns) for table in tables)
    row = BindingSuggestion(
        id=uuid4(),
        ontology_id=ontology_id,
        data_source_id=source.id,
        user_id=user_id,
        scope=scope,
        status="queued",
        proposed=0,
        dropped=0,
        samples_sent=False,
        created_at=_now(),
    )
    db.add(row)
    await db.flush()
    audit.record(
        db,
        "binding.suggested",
        actor_id=user_id,
        target_type="ontology",
        target_id=str(ontology_id),
        detail={
            "suggestionId": str(row.id),
            "dataSourceId": str(source.id),
            "tables": len(tables),
            "columns": columns,
            # Whether the job will read sample values and send them to the model.
            "samples": source.allow_samples,
        },
        ip=ip,
    )
    await jobs.enqueue(db, JOB_KIND, {"suggestionId": str(row.id)})
    await db.commit()
    return _out(row)


async def get_request(
    db: AsyncSession,
    suggestion_id: UUID,
    *,
    user_id: UUID,
) -> schemas.BindingSuggestion:
    """A request of the user's own (404 `binding_suggestion.not_found` for others')."""
    row = await db.get(BindingSuggestion, suggestion_id)
    if row is None or row.user_id != user_id:
        raise _not_found()
    return _out(row)


async def list_requests(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    user_id: UUID,
    limit: int,
) -> list[schemas.BindingSuggestion]:
    """The user's latest requests about the ontology, newest first."""
    statement = (
        select(BindingSuggestion)
        .where(BindingSuggestion.ontology_id == ontology_id, BindingSuggestion.user_id == user_id)
        .order_by(BindingSuggestion.created_at.desc(), BindingSuggestion.id.desc())
        .limit(limit)
    )
    return [_out(row) for row in await db.scalars(statement)]


# ---------- what the job works on ----------


@dataclass
class _Relation:
    """A relation of a type to bind, oriented as the binding will be: source = domain side."""

    element: Element
    source_type: UUID
    target_type: UUID

    @property
    def key(self) -> tuple[UUID, UUID, UUID]:
        return (self.element.id, self.source_type, self.target_type)


@dataclass(frozen=True, slots=True)
class _Request:
    """What the job needs of the stored request, read once at its start."""

    id: UUID
    ontology_id: UUID
    data_source_id: UUID
    user_id: UUID
    scope: dict[str, Any]


@dataclass
class _Type:
    element: Element
    # The existing type binding: its element id and table; None while the type has none.
    bound_id: UUID | None
    bound_table: Table | None
    properties: list[Element]
    bound_columns: list[str]
    relations: list[_Relation]
    # Bound outside the request: only an end of the relations of the requested types.
    anchor: bool = False


@dataclass
class _Plan:
    source: DataSourceRef
    tables: dict[TableKey, Table]
    types: list[_Type]
    elements: dict[UUID, Element]


# Why this module left a suggestion out (binding_proposals adds the binding.* codes).
UNKNOWN_ELEMENT = "suggestion.unknown_element"  # an id that was not shown as a candidate
NOT_IN_CATALOG = "suggestion.not_in_catalog"  # a table, column or join the catalog lacks
REPEATED = "suggestion.repeated"  # more candidates for one place than are tried
# Candidates tried per place (a type's table, a property's column, a relation's join), in the
# model's order: the first that passes the binding rules is taken.
CANDIDATES_MAX = 3


@dataclass
class _Draft:
    """The suggestions taken up so far, and why the others were left out."""

    # type id → (temp_ref or bound element id, table)
    tables: dict[UUID, tuple[str, Table]] = field(default_factory=dict)
    items: list[ProposedItem] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)
    # Candidates taken per place.
    claimed: Counter[object] = field(default_factory=Counter)


def _key(table: Table) -> TableKey:
    return (table.schema_name, table.name)


async def _type_view(db: AsyncSession, ontology_id: UUID, type_id: UUID) -> TypeBindingView:
    (view,) = await ontology_bindings.binding_views(db, ontology_id, type_id)
    return view


async def _plan(db: AsyncSession, row: _Request) -> _Plan:
    """The catalog step: the tables in scope, and what the working version still lacks."""
    source = await _usable_source(db, row.data_source_id)
    found = await _scope_tables(db, source.id, row.scope)
    # A schema may have grown since the request, with a refresh of the catalog.
    _check_size(found)
    tables = {_key(t): t for t in found}
    everything = [
        element
        for kind in ("entity_type", "property", "relation_type")
        for element in await ontology.list_elements(db, row.ontology_id, kind=kind, q=None)
    ]
    by_id = {element.id: element for element in everything}
    wanted = {UUID(value) for value in row.scope.get("typeIds") or ()}
    types: list[_Type] = []
    for element in everything:
        if element.kind != "entity_type":
            continue
        view = await _type_view(db, row.ontology_id, element.id)
        requested = not wanted or element.id in wanted
        bound_table: Table | None = None
        if view.table is not None:
            if view.table.data_source.id != source.id:
                continue
            ref = CatalogRef(schema=view.table.schema_name, name=view.table.table)
            bound_table = tables.get((ref.schema, ref.name))
            if bound_table is None:
                # Out of scope: no suggestions for the type itself, but it still anchors the
                # relations of the requested types to it.
                requested = False
                bound_table = await connectors.get_catalog_table(db, source.id, ref)
                if bound_table is None:
                    continue
        elif not requested:
            continue
        properties = [
            by_id[p.property_id]
            for p in view.properties
            if p.column is None and p.property_id in by_id
        ]
        relations = [
            _Relation(
                element=by_id[r.relation_id],
                source_type=element.id if r.direction == "out" else r.other_type_id,
                target_type=r.other_type_id if r.direction == "out" else element.id,
            )
            for r in view.relations
            if r.join is None and r.relation_id in by_id
        ]
        types.append(
            _Type(
                element=element,
                bound_id=view.table.element_id if view.table is not None else None,
                bound_table=bound_table,
                properties=properties if requested else [],
                bound_columns=sorted({p.column.column for p in view.properties if p.column}),
                relations=relations if requested else [],
                anchor=not requested,
            )
        )
    return _Plan(source=source, tables=tables, types=types, elements=by_id)


# ---------- what the model is shown ----------


def _definition(element: Element) -> str | None:
    text = element.definition_zh or element.definition_en
    return text[:DEFINITION_MAX_LENGTH] if text else None


def _element_text(element: Element, plan: _Plan) -> dict[str, Any]:
    shown: dict[str, Any] = {
        "id": str(element.id),
        "localName": element.local_name,
        "labelZh": element.label_zh,
        "labelEn": element.label_en,
        "synonyms": [synonym.text for synonym in element.synonyms],
        "definition": _definition(element),
    }
    if element.kind == "entity_type" and element.parent_id in plan.elements:
        shown["parent"] = str(element.parent_id)
    if element.kind == "property":
        shown["domainId"] = str(element.domain_id) if element.domain_id is not None else None
        shown["datatype"] = element.datatype
        shown["unit"] = element.unit
    return shown


def _comment(text: str | None) -> str | None:
    return text[:COMMENT_MAX_LENGTH] if text else None


def _table_text(table: Table, samples: dict[str, list[str]] | None = None) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    for column in table.columns:
        shown: dict[str, Any] = {
            "name": column.name,
            "type": column.type,
            "nullable": column.nullable,
            "comment": _comment(column.comment),
        }
        if samples and samples.get(column.name):
            shown["samples"] = samples[column.name]
        columns.append(shown)
    return {
        "schema": table.schema_name,
        "table": table.name,
        "kind": table.kind,
        "comment": _comment(table.comment),
        "primaryKey": list(table.primary_key) if table.primary_key else None,
        "columns": columns,
        "foreignKeys": [
            {
                "columns": fk.columns,
                "references": f"{fk.ref_schema}.{fk.ref_table}",
                "referencedColumns": fk.ref_columns,
            }
            for fk in table.foreign_keys
        ],
    }


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _match_text(plan: _Plan, types: Sequence[_Type]) -> str:
    return (
        "Object types to match:\n"
        + _dumps([_element_text(t.element, plan) for t in types])
        + "\n\nTables:\n"
        + _dumps([_table_text(table) for table in plan.tables.values()])
    )


def _references(table: Table, other: Table) -> bool:
    return any((fk.ref_schema, fk.ref_table) == _key(other) for fk in table.foreign_keys)


def _link_tables(plan: _Plan, source: Table, target: Table) -> list[Table]:
    """Tables in scope that reference both ends: candidates for a link table."""
    return [
        table
        for table in plan.tables.values()
        if _key(table) not in (_key(source), _key(target))
        and _references(table, source)
        and _references(table, target)
    ]


def _columns_text(
    plan: _Plan,
    kind: _Type,
    table: Table,
    relations: Sequence[tuple[_Relation, Table, Table]],
    samples: dict[TableKey, dict[str, list[str]]],
) -> str:
    others: dict[TableKey, Table] = {}
    shown_relations: list[dict[str, Any]] = []
    for relation, source, target in relations:
        for end in (source, target, *_link_tables(plan, source, target)):
            if _key(end) != _key(table):
                others[_key(end)] = end
        shown_relations.append(
            {
                **_element_text(relation.element, plan),
                "sourceTypeId": str(relation.source_type),
                "sourceTable": f"{source.schema_name}.{source.name}",
                "targetTypeId": str(relation.target_type),
                "targetTable": f"{target.schema_name}.{target.name}",
            }
        )
    parts = [
        "Object type:\n" + _dumps(_element_text(kind.element, plan)),
        "Its table:\n" + _dumps(_table_text(table, samples.get(_key(table)))),
        "Properties to map:\n" + _dumps([_element_text(p, plan) for p in kind.properties]),
        "Relations to map:\n" + _dumps(shown_relations),
    ]
    if kind.bound_columns:
        parts.append("Columns already bound for this type:\n" + _dumps(kind.bound_columns))
    if others:
        parts.append(
            "Other tables the relations may use:\n"
            + _dumps([_table_text(other) for other in others.values()])
        )
    return "\n\n".join(parts)


# ---------- taking up the model's answers ----------


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value.strip())
    except ValueError:
        return None


def _clamp(confidence: float) -> float:
    return min(max(confidence, 0.0), 1.0)


def _rationale(text: str) -> str | None:
    return text.strip()[:RATIONALE_MAX_LENGTH] or None


def _quote(text: str) -> str:
    return text[:QUOTE_MAX_LENGTH]


def _has(table: Table, columns: Iterable[str]) -> bool:
    names = {column.name for column in table.columns}
    listed = list(columns)
    return bool(listed) and len(set(listed)) == len(listed) and all(c in names for c in listed)


def _evidence(
    source: DataSourceRef, table: Table, fact: str, quote: str, column: str | None = None
) -> EvidenceIn:
    return EvidenceIn(
        kind="catalog",
        source=CatalogEvidenceSource.model_validate(
            {
                "dataSourceId": source.id,
                "schema": table.schema_name,
                "table": table.name,
                "column": column,
                "fact": fact,
            }
        ),
        quote=_quote(quote),
    )


def _with_comment(text: str, comment: str | None) -> str:
    return f"{text}，注释：{comment}" if comment else text


def _table_evidence(source: DataSourceRef, table: Table) -> list[EvidenceIn]:
    found = [
        _evidence(
            source,
            table,
            "table",
            _with_comment(f"{table.kind.upper()} {table.schema_name}.{table.name}", table.comment),
        )
    ]
    if table.primary_key:
        found.append(
            _evidence(source, table, "primary_key", f"PRIMARY KEY ({', '.join(table.primary_key)})")
        )
    return found


def _column_evidence(
    source: DataSourceRef,
    table: Table,
    name: str,
    samples: dict[TableKey, dict[str, list[str]]],
) -> list[EvidenceIn]:
    column = next(c for c in table.columns if c.name == name)
    text = f"{column.name} {column.type}{'' if column.nullable else ' NOT NULL'}"
    found = [_evidence(source, table, "column", _with_comment(text, column.comment), name)]
    values = samples.get(_key(table), {}).get(name)
    if values:
        found.append(_evidence(source, table, "sample", f"{name}：{'、'.join(values)}", name))
    return found


def _foreign_key_evidence(
    source: DataSourceRef, holder: Table, columns: list[str], referenced: Table, refs: list[str]
) -> list[EvidenceIn]:
    """The declared foreign key, or else the columns on both sides: facts of the catalog."""
    for fk in holder.foreign_keys:
        if (
            fk.columns == columns
            and (fk.ref_schema, fk.ref_table) == _key(referenced)
            and fk.ref_columns == refs
        ):
            quote = (
                f"FOREIGN KEY ({', '.join(columns)}) REFERENCES "
                f"{referenced.schema_name}.{referenced.name} ({', '.join(refs)})"
            )
            return [_evidence(source, holder, "foreign_key", quote)]
    return [
        *(e for name in columns for e in _column_evidence(source, holder, name, {})),
        *(e for name in refs for e in _column_evidence(source, referenced, name, {})),
    ]


type _TableCandidate = tuple[UUID, str, Table, ProposedItem]


def _take_tables(
    plan: _Plan, types: Sequence[_Type], output: MatchOut, draft: _Draft
) -> list[_TableCandidate]:
    """The type bindings worth checking, at most CANDIDATES_MAX per type."""
    candidates = {t.element.id: t for t in types}
    found: list[_TableCandidate] = []
    for match in output.matches:
        type_id = _uuid(match.type_id)
        table = plan.tables.get((match.schema_name.strip(), match.table.strip()))
        if type_id is None or type_id not in candidates:
            draft.dropped[UNKNOWN_ELEMENT] += 1
            continue
        if draft.claimed[("table", type_id)] >= CANDIDATES_MAX:
            draft.dropped[REPEATED] += 1
            continue
        if table is None:
            draft.dropped[NOT_IN_CATALOG] += 1
            continue
        if table.primary_key:
            # The table's own key, whatever the model chose.
            keys, flags = list(table.primary_key), []
        else:
            keys, flags = [c.strip() for c in match.key_columns], ["key_unverified"]
            if not _has(table, keys):
                draft.dropped[NOT_IN_CATALOG] += 1
                continue
        ref = f"new:table:{len(found) + 1}"
        try:
            binding = TableBinding.model_validate(
                {
                    "target": "table",
                    "dataSourceId": plan.source.id,
                    "schema": table.schema_name,
                    "table": table.name,
                    "keyColumns": keys,
                }
            )
        except ValidationError:
            draft.dropped[NOT_IN_CATALOG] += 1
            continue
        draft.claimed[("table", type_id)] += 1
        item = ProposedItem(
            op="create",
            kind="type_binding",
            temp_ref=ref,
            proposed=ElementFields(subject_ref=str(type_id), binding=binding),
            confidence=_clamp(match.confidence),
            rationale=_rationale(match.rationale),
            flags=flags,
            evidence=_table_evidence(plan.source, table),
        )
        found.append((type_id, ref, table, item))
    return found


def _join(
    output: RelationMatchOut, source: Table, target: Table, plan: _Plan
) -> tuple[JoinBinding, list[EvidenceIn]] | None:
    """The model's join when every table and column it names is there; else None."""
    if (output.foreign_key is None) == (output.link_table is None):
        return None
    try:
        if output.foreign_key is not None:
            fk = output.foreign_key
            holder, referenced = (source, target) if fk.side == "source" else (target, source)
            columns = [c.strip() for c in fk.columns]
            refs = [c.strip() for c in fk.references]
            if len(columns) != len(refs) or not _has(holder, columns) or not _has(referenced, refs):
                return None
            join: ForeignKeyJoin | LinkTableJoin = ForeignKeyJoin(
                kind="foreign_key", side=fk.side, columns=columns, references=refs
            )
            evidence = _foreign_key_evidence(plan.source, holder, columns, referenced, refs)
        elif (link := output.link_table) is not None:
            table = plan.tables.get((link.schema_name.strip(), link.table.strip()))
            source_columns = [c.strip() for c in link.source_columns]
            target_columns = [c.strip() for c in link.target_columns]
            if table is None or not _has(table, source_columns) or not _has(table, target_columns):
                return None
            join = LinkTableJoin.model_validate(
                {
                    "kind": "link_table",
                    "schema": table.schema_name,
                    "table": table.name,
                    "sourceColumns": source_columns,
                    "targetColumns": target_columns,
                }
            )
            evidence = [
                *_table_evidence(plan.source, table)[:1],
                *(
                    e
                    for end, names in ((source, source_columns), (target, target_columns))
                    for e in _link_evidence(plan.source, table, names, end)
                ),
            ]
        else:
            return None
    except ValidationError:
        return None
    return JoinBinding(target="join", join=join), evidence


def _link_evidence(
    source: DataSourceRef, link: Table, names: list[str], end: Table
) -> list[EvidenceIn]:
    for fk in link.foreign_keys:
        if fk.columns == names and (fk.ref_schema, fk.ref_table) == _key(end):
            return _foreign_key_evidence(source, link, names, end, fk.ref_columns)
    return [e for name in names for e in _column_evidence(source, link, name, {})]


def _take_columns(
    plan: _Plan,
    kind: _Type,
    ref: str,
    table: Table,
    relations: dict[tuple[UUID, UUID, UUID], tuple[_Relation, Table, Table]],
    output: ColumnsOut,
    samples: dict[TableKey, dict[str, list[str]]],
    draft: _Draft,
) -> None:
    properties = {p.id: p for p in kind.properties}
    for match in output.properties:
        property_id = _uuid(match.property_id)
        column = match.column.strip()
        claim = (kind.element.id, property_id)
        names = {c.name for c in table.columns}
        if property_id not in properties:
            draft.dropped[UNKNOWN_ELEMENT] += 1
            continue
        if draft.claimed[claim] >= CANDIDATES_MAX:
            draft.dropped[REPEATED] += 1
            continue
        try:
            if column not in names:
                raise ValueError(column)
            binding = ColumnBinding(target="column", column=column)
        except ValueError:  # ValidationError is one
            draft.dropped[NOT_IN_CATALOG] += 1
            continue
        draft.claimed[claim] += 1
        draft.items.append(
            ProposedItem(
                op="create",
                kind="property_binding",
                proposed=ElementFields(
                    subject_ref=str(property_id),
                    parent_ref=ref,
                    binding=binding,
                ),
                confidence=_clamp(match.confidence),
                rationale=_rationale(match.rationale),
                evidence=_column_evidence(plan.source, table, column, samples),
            )
        )
    for output_relation in output.relations:
        ids = (
            _uuid(output_relation.relation_id),
            _uuid(output_relation.source_type_id),
            _uuid(output_relation.target_type_id),
        )
        found = relations.get(cast(tuple[UUID, UUID, UUID], ids))
        if found is None:
            draft.dropped[UNKNOWN_ELEMENT] += 1
            continue
        if draft.claimed[ids] >= CANDIDATES_MAX:
            draft.dropped[REPEATED] += 1
            continue
        joined = _join(output_relation, found[1], found[2], plan)
        if joined is None:
            draft.dropped[NOT_IN_CATALOG] += 1
            continue
        draft.claimed[ids] += 1
        relation, _, _ = found
        join_binding, evidence = joined
        draft.items.append(
            ProposedItem(
                op="create",
                kind="relation_binding",
                proposed=ElementFields(
                    subject_ref=str(relation.element.id),
                    domain_ref=draft.tables[relation.source_type][0],
                    range_ref=draft.tables[relation.target_type][0],
                    binding=join_binding,
                ),
                confidence=_clamp(output_relation.confidence),
                rationale=_rationale(output_relation.rationale),
                evidence=evidence,
            )
        )


# ---------- sample values ----------


def _sample_text(value: object) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


async def _read_samples(
    session_factory: async_sessionmaker[AsyncSession],
    job: JobContext,
    row: _Request,
    tables: Iterable[Table],
) -> dict[TableKey, dict[str, list[str]]]:
    """Sample values of the tables the columns step works on, one read per table, each read
    audited. Only while the data source allows samples; a table that cannot be read is left
    without them."""
    found: dict[TableKey, dict[str, list[str]]] = {}
    for table in tables:
        columns = tuple(column.name for column in table.columns)
        async with session_factory() as db:
            try:
                values = await connectors.sample_values(
                    db,
                    row.data_source_id,
                    CatalogRef(schema=table.schema_name, name=table.name),
                    columns,
                )
            except SourceDisabledError:
                break  # switched off, or the data source archived, since the request
            except ConnectorError:
                values = None
        async with session_factory.begin() as db:
            await job.check_lease(db)
            audit.record(
                db,
                "datasource.sampled",
                actor_id=row.user_id,
                target_type="data_source",
                target_id=str(row.data_source_id),
                detail={
                    "suggestionId": str(row.id),
                    "tables": 1,
                    "columns": len(columns),
                    "succeeded": values is not None,
                },
            )
        if values is not None:
            found[_key(table)] = {
                name: [_sample_text(value) for value in shown]
                for name, shown in values.items()
                if shown
            }
    return found


# ---------- the job ----------


async def _set(
    session_factory: async_sessionmaker[AsyncSession],
    job: JobContext,
    suggestion_id: UUID,
    **values: Any,
) -> None:
    async with session_factory.begin() as db:
        await job.check_lease(db)
        row = await db.get(BindingSuggestion, suggestion_id, with_for_update=True)
        if row is not None:
            for name, value in values.items():
                setattr(row, name, value)


async def _suggest(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    model: str,
    job: JobContext,
    row: _Request,
) -> tuple[_Draft, bool, str]:
    async with session_factory() as db:
        plan = await _plan(db, row)
    draft = _Draft()
    for kind in plan.types:
        if kind.bound_id is not None and kind.bound_table is not None:
            draft.tables[kind.element.id] = (str(kind.bound_id), kind.bound_table)
    requested = [t for t in plan.types if not t.anchor]
    unbound = [t for t in requested if t.bound_id is None]
    if unbound and plan.tables:
        await _set(session_factory, job, row.id, step="match")
        matched = await gateway.structured(
            purpose=MATCH_PURPOSE,
            model=model,
            instructions=MATCH_INSTRUCTIONS,
            text=_match_text(plan, unbound),
            schema=MatchOut,
        )
        found = _take_tables(plan, unbound, matched, draft)
        if found:
            # The columns step maps the columns of one table per type: settle it first.
            async with session_factory() as db:
                chosen = await binding_proposals.first_passing(
                    db, row.ontology_id, [item for *_, item in found]
                )
            draft.dropped.update(d.code for d in chosen.dropped)
            for position in chosen.taken:
                type_id, ref, table, item = found[position]
                draft.tables[type_id] = (ref, table)
                draft.items.append(item)
    await _set(session_factory, job, row.id, step="columns")
    work = [
        (kind, draft.tables[kind.element.id])
        for kind in requested
        if kind.element.id in draft.tables and (kind.properties or kind.relations)
    ]
    samples: dict[TableKey, dict[str, list[str]]] = {}
    if plan.source.allow_samples and work:
        # A type and its subtype may share a table: one read each.
        tables = {_key(table): table for _, (_, table) in work}
        samples = await _read_samples(session_factory, job, row, tables.values())
    sent = False
    for kind, (ref, table) in work:
        relations: dict[tuple[UUID, UUID, UUID], tuple[_Relation, Table, Table]] = {}
        for relation in kind.relations:
            ends = draft.tables.get(relation.source_type), draft.tables.get(relation.target_type)
            if ends[0] is not None and ends[1] is not None and relation.key not in draft.claimed:
                relations[relation.key] = (relation, ends[0][1], ends[1][1])
        if not kind.properties and not relations:
            continue
        if samples and not await _samples_allowed(session_factory, row.data_source_id):
            samples = {}  # switched off while the job runs: none sent from here on
        sent = sent or bool(samples.get(_key(table)))
        output = await gateway.structured(
            purpose=COLUMNS_PURPOSE,
            model=model,
            instructions=COLUMNS_INSTRUCTIONS,
            text=_columns_text(plan, kind, table, list(relations.values()), samples),
            schema=ColumnsOut,
        )
        _take_columns(plan, kind, ref, table, relations, output, samples, draft)
    return draft, sent, plan.source.name


async def _samples_allowed(
    session_factory: async_sessionmaker[AsyncSession], data_source_id: UUID
) -> bool:
    async with session_factory() as db:
        source = await connectors.get_data_source_ref(db, data_source_id)
    return source is not None and source.status == "active" and source.allow_samples


def make_handler(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    model: str,
) -> Callable[[JobContext], Awaitable[None]]:
    """The handler of `bindings.suggest` jobs."""

    async def handle(job: JobContext) -> None:
        suggestion_id = UUID(job.payload["suggestionId"])
        async with session_factory.begin() as db:
            await job.check_lease(db)
            row = await db.get(BindingSuggestion, suggestion_id, with_for_update=True)
            if row is None or row.status in ("succeeded", "failed"):
                return  # a replayed job: the request has its answer
            # Only reachable through stale-lease recovery: earlier runs died without reporting.
            interrupted = job.attempts > job.max_attempts
            if interrupted:
                row.status, row.error_code, row.finished_at = "failed", "internal.error", _now()
            else:
                row.status, row.step = "running", "catalog"
            request = _Request(row.id, row.ontology_id, row.data_source_id, row.user_id, row.scope)
        if interrupted:
            raise AppError(500, "internal.error", "The suggestion was interrupted too often.")
        try:
            draft, samples_sent, source_name = await _suggest(
                session_factory, gateway, model, job, request
            )
            async with session_factory.begin() as db:
                await job.check_lease(db)
                stored = await db.get(BindingSuggestion, suggestion_id, with_for_update=True)
                if stored is None:
                    return
                stored.step = "changeset"
                proposal = await binding_proposals.propose_bindings(
                    db,
                    request.ontology_id,
                    items=draft.items,
                    created_by=request.user_id,
                    title=f"AI 绑定建议：{source_name}",
                )
                reasons = draft.dropped + Counter(d.code for d in proposal.dropped)
                stored.status = "succeeded"
                stored.change_set_id = proposal.change_set_id
                stored.proposed = proposal.proposed
                stored.dropped = reasons.total()
                stored.samples_sent = samples_sent
                stored.finished_at = _now()
                # What became of the suggestions and why the others were left out: counts only,
                # nothing the model said and no sample values.
                audit.record(
                    db,
                    "binding.suggestion_finished",
                    actor_id=request.user_id,
                    target_type="ontology",
                    target_id=str(request.ontology_id),
                    detail={
                        "suggestionId": str(suggestion_id),
                        "changeSetId": (
                            str(proposal.change_set_id) if proposal.change_set_id else None
                        ),
                        "proposed": proposal.proposed,
                        "dropped": reasons.total(),
                        "reasons": dict(sorted(reasons.items())),
                    },
                )
        except AiError as exc:
            if exc.retryable and job.attempts < job.max_attempts:
                await _set(session_factory, job, suggestion_id, status="queued")
                raise RetryableJobError(exc.code) from exc
            await _fail(session_factory, job, suggestion_id, exc.code)
            raise AppError(422, exc.code, str(exc)) from exc
        except Exception as exc:
            code = exc.code if isinstance(exc, AppError) else "internal.error"
            await _fail(session_factory, job, suggestion_id, code)
            raise

    return handle


async def _fail(
    session_factory: async_sessionmaker[AsyncSession],
    job: JobContext,
    suggestion_id: UUID,
    code: str,
) -> None:
    await _set(
        session_factory,
        job,
        suggestion_id,
        status="failed",
        error_code=code[:64],
        finished_at=_now(),
    )
