"""Data bindings as other code reads them (spec 003, 6.5 and 6.6).

- `table_usage`: which tables of a data source are bound to which object types; main.py and
  worker.py register it as the connectors module's usage provider (connectors must not import
  ontology).
- `bound_model` and `released_ontology`: the bindings and the ontology of the release in
  effect, for querying (batch 5) and MCP (batch 6a). Unreviewed, unmerged and unpublished
  bindings never reach them: they read the release snapshot only.
- Labels of binding elements ("炉次 → mes.heat"), and the binding deletes an import or a Turtle
  edit brings along with the elements it deletes.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.schemas import CatalogTableCopy
from ontology_platform.modules.connectors.service import TableUsage
from ontology_platform.modules.connectors.statements import TableRef
from ontology_platform.modules.ontology import binding_rules, rules, schemas, service
from ontology_platform.modules.ontology.models import (
    BINDING_KINDS,
    SEMANTIC_KINDS,
    ChangeItem,
    ChangeSet,
    Datatype,
    Element,
    Kind,
    Ontology,
    Release,
)
from ontology_platform.modules.ontology.schemas import JoinBinding


def _label(row: Mapping[str, Any]) -> str:
    return rules.display_label(row.get("labelZh"), row.get("labelEn"), row.get("localName"))


# ---------- labels ----------


def _table(binding: Mapping[str, Any] | None) -> str | None:
    if not binding or binding.get("target") != "table":
        return None
    return f"{binding.get('schema')}.{binding.get('table')}"


def binding_label(
    kind: str,
    binding: Mapping[str, Any] | None,
    subject: str,
    *,
    parent: Mapping[str, Any] | None = None,
    source: Mapping[str, Any] | None = None,
    target: Mapping[str, Any] | None = None,
) -> str:
    """What a binding element is called where elements are listed: the bound element and where
    it lives, e.g. "炉次 → mes.heat", "重量 → mes.heat.weight_t". `parent`, `source` and
    `target` are the bindings of the type bindings it hangs under, when known."""
    binding = binding or {}
    if kind == "type_binding":
        where = _table(binding)
    elif kind == "property_binding":
        table = _table(parent)
        column = str(binding.get("column", ""))
        where = f"{table}.{column}" if table else column
    else:
        join = binding.get("join") or {}
        if join.get("kind") == "link_table":
            where = f"{join.get('schema')}.{join.get('table')}"
        else:
            holder = _table(source if join.get("side") == "source" else target)
            columns = ", ".join(join.get("columns") or [])
            where = f"{holder}.{columns}" if holder else columns
    return f"{subject} → {where}" if where else subject


def element_label(element: Element, by_id: Mapping[UUID, Element]) -> str:
    """The label of a binding element among the elements `by_id`."""

    def binding_of(element_id: UUID | None) -> Mapping[str, Any] | None:
        other = by_id.get(element_id) if element_id is not None else None
        return other.binding if other is not None else None

    subject = by_id.get(element.subject_id) if element.subject_id else None
    name = (
        rules.display_label(subject.label_zh, subject.label_en, subject.local_name)
        if subject is not None
        else ""
    )
    return binding_label(
        element.kind,
        element.binding,
        name,
        parent=binding_of(element.parent_id),
        source=binding_of(element.domain_id),
        target=binding_of(element.range_id),
    )


def row_label(row: Mapping[str, Any], rows: Mapping[str, Mapping[str, Any]]) -> str:
    """The label of a binding as a snapshot row (camelCase JSON) among `rows` (by id)."""

    def binding_of(key: str) -> Mapping[str, Any] | None:
        other = rows.get(str(row.get(key))) if row.get(key) else None
        return other.get("binding") if other is not None else None

    subject = rows.get(str(row.get("subjectId")))
    return binding_label(
        str(row["kind"]),
        row.get("binding"),
        _label(subject) if subject is not None else "",
        parent=binding_of("parentId"),
        source=binding_of("domainId"),
        target=binding_of("rangeId"),
    )


# ---------- cascades ----------


def cascade_deletes(
    elements: Iterable[Element], deleted: Iterable[UUID]
) -> list[schemas.ProposedItem]:
    """Deletes of the active bindings that refer to the `deleted` elements, directly or through
    another binding deleted along. Imports and Turtle edits diff the semantic kinds only; this
    brings the bindings of what they delete (spec 003, 6.1)."""
    bindings = [e for e in elements if e.kind in BINDING_KINDS and e.status == "active"]
    leaving = set(deleted)
    found: list[Element] = []
    changed = True
    while changed:
        changed = False
        for element in bindings:
            if element.id in leaving:
                continue
            refs = (element.subject_id, element.parent_id, element.domain_id, element.range_id)
            if leaving.intersection(ref for ref in refs if ref is not None):
                leaving.add(element.id)
                found.append(element)
                changed = True
    return [
        schemas.ProposedItem(
            op="delete",
            kind=cast(Kind, element.kind),
            target_element_id=element.id,
            target_revision=element.revision,
            proposed=schemas.ElementFields(),
        )
        for element in found
    ]


# ---------- the binding view of the working version (type details) ----------


class _Checks:
    """Data sources and cached catalog tables, each read once, and how bindings match them."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._sources: dict[str, schemas.BoundDataSource | None] = {}
        self._ready: dict[str, bool] = {}
        self._tables: dict[tuple[str, str, str], CatalogTableCopy | None] = {}

    async def source(self, source_id: str) -> schemas.BoundDataSource | None:
        if source_id not in self._sources:
            ref = await connectors.get_data_source_ref(self._db, UUID(source_id))
            self._ready[source_id] = ref is not None and ref.catalog_status == "ready"
            self._sources[source_id] = (
                schemas.BoundDataSource(id=ref.id, name=ref.name, status=ref.status)
                if ref is not None
                else None
            )
        return self._sources[source_id]

    async def table(
        self, table: Mapping[str, Any] | None, schema: str | None = None, name: str | None = None
    ) -> tuple[CatalogTableCopy | None, schemas.CatalogCheck]:
        """A table of a type binding (or `schema.name` in its data source) and why it is
        missing: the table is gone, or the catalog has never been read."""
        if not table:
            return None, "catalog_unavailable"
        source_id = str(table["dataSourceId"])
        await self.source(source_id)
        key = (source_id, schema or str(table["schema"]), name or str(table["table"]))
        if key not in self._tables:
            self._tables[key] = await connectors.get_catalog_table(
                self._db, UUID(source_id), TableRef(schema=key[1], name=key[2])
            )
        found = self._tables[key]
        if found is not None:
            return found, "ok"
        return None, "missing_table" if self._ready[source_id] else "catalog_unavailable"


def _has(table: CatalogTableCopy, columns: Iterable[str]) -> bool:
    names = {column.name for column in table.columns}
    return all(column in names for column in columns)


async def _join_check(
    checks: _Checks,
    join: Mapping[str, Any],
    source: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None,
) -> schemas.CatalogCheck:
    if join.get("kind") == "link_table":
        link, check = await checks.table(source, str(join["schema"]), str(join["table"]))
        if link is None:
            return check
        columns = [*join["sourceColumns"], *join["targetColumns"]]
        return "ok" if _has(link, columns) else "missing_column"
    source_table, check = await checks.table(source)
    if source_table is None:
        return check
    target_table, check = await checks.table(target)
    if target_table is None:
        return check
    holder, other = (
        (source_table, target_table)
        if join.get("side") == "source"
        else (target_table, source_table)
    )
    found = _has(holder, join["columns"]) and _has(other, join["references"])
    return "ok" if found else "missing_column"


def _related_types(items: Iterable[ChangeItem], elements: Mapping[UUID, Element]) -> set[UUID]:
    """The object types an open change set's binding items are about."""

    def type_of(binding_id: UUID | None) -> UUID | None:
        element = elements.get(binding_id) if binding_id is not None else None
        if element is None:
            return None
        if element.kind == "type_binding":
            return element.subject_id
        return type_of(element.parent_id or element.domain_id)

    listed = [item for item in items if item.kind in BINDING_KINDS]
    fields = {item.id: rules.effective_fields(item.proposed, item.edited) for item in listed}
    created = {
        item.temp_ref: fields[item.id].subject_ref
        for item in listed
        if item.kind == "type_binding" and item.temp_ref
    }
    found: set[UUID] = set()
    for item in listed:
        if item.target_element_id is not None:
            ends: list[UUID | None] = [item.target_element_id]
            target = elements.get(item.target_element_id)
            if target is not None and target.kind == "relation_binding":
                ends.append(target.range_id)
            found.update(t for end in ends if (t := type_of(end)) is not None)
            continue
        own = fields[item.id]
        refs: list[str | None] = [own.subject_ref] if item.kind == "type_binding" else []
        refs += [own.parent_ref, own.domain_ref, own.range_ref]
        for ref in refs:
            if ref is None:
                continue
            element_id = rules.parse_id(ref)
            if element_id is None:
                subject = created.get(ref)
                element_id = rules.parse_id(subject) if subject else None
            elif element_id in elements and elements[element_id].kind == "type_binding":
                element_id = type_of(element_id)
            if element_id is not None:
                found.add(element_id)
    return found


async def binding_views(
    db: AsyncSession, ontology_id: UUID, type_id: UUID | None
) -> list[schemas.TypeBindingView]:
    """The bindings of one object type (`type_id`), or of every bound object type, in the
    working version, each checked against the cached catalog (spec 003, 6.5)."""
    await service._ontology_or_404(db, ontology_id)
    everything = await service._elements(db, ontology_id, all_kinds=True)
    by_id = {element.id: element for element in everything}
    active = [element for element in everything if element.status == "active"]
    tables = {e.subject_id: e for e in active if e.kind == "type_binding" and e.subject_id}
    if type_id is not None:
        chosen = by_id.get(type_id)
        if chosen is None or chosen.kind != "entity_type" or chosen.status != "active":
            raise AppError(404, "element.not_found", "Element not found.")
        types = [chosen]
    else:
        types = sorted(
            (by_id[subject] for subject in tables if subject in by_id),
            key=lambda e: (_element_name(e), str(e.id)),
        )
    open_items = await db.execute(
        select(ChangeItem, ChangeSet.id)
        .join(ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
        .where(
            ChangeSet.ontology_id == ontology_id,
            ChangeSet.status == "open",
            ChangeItem.kind.in_(BINDING_KINDS),
        )
        .order_by(ChangeSet.created_at, ChangeSet.id)
    )
    by_change_set: dict[UUID, list[ChangeItem]] = {}
    for item, change_set_id in open_items:
        by_change_set.setdefault(change_set_id, []).append(item)
    pending = {
        change_set_id: _related_types(items, by_id)
        for change_set_id, items in by_change_set.items()
    }
    checks = _Checks(db)
    return [await _view(checks, element, active, by_id, tables, pending) for element in types]


def _element_name(element: Element) -> str:
    return rules.display_label(element.label_zh, element.label_en, element.local_name)


def _ancestors(element: Element, by_id: Mapping[UUID, Element]) -> list[UUID]:
    """The type and the types above it, nearest first."""
    found: list[UUID] = []
    current: Element | None = element
    while current is not None and current.id not in found:
        found.append(current.id)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return found


async def _view(
    checks: _Checks,
    entity: Element,
    active: Sequence[Element],
    by_id: Mapping[UUID, Element],
    tables: Mapping[UUID, Element],
    pending: Mapping[UUID, set[UUID]],
) -> schemas.TypeBindingView:
    lineage = _ancestors(entity, by_id)
    own = tables.get(entity.id)
    table_binding = own.binding if own is not None else None
    table_view: schemas.TableBindingView | None = None
    catalog_table: CatalogTableCopy | None = None
    table_check: schemas.CatalogCheck = "catalog_unavailable"
    if own is not None and table_binding:
        catalog_table, table_check = await checks.table(table_binding)
        keys = list(table_binding.get("keyColumns") or [])
        if catalog_table is not None and not _has(catalog_table, keys):
            table_check = "missing_column"
        source_id = str(table_binding["dataSourceId"])
        source = await checks.source(source_id) or schemas.BoundDataSource(
            id=UUID(source_id), name="", status="archived"
        )
        table_view = schemas.TableBindingView.model_validate(
            {
                "element_id": own.id,
                "revision": own.revision,
                "data_source": source,
                "schema_name": str(table_binding["schema"]),
                "table": str(table_binding["table"]),
                "key_columns": keys,
                "check": table_check,
            }
        )
    columns = {
        e.subject_id: e
        for e in active
        if own is not None and e.kind == "property_binding" and e.parent_id == own.id
    }
    properties: list[schemas.PropertyBindingView] = []
    for prop in active:
        if prop.kind != "property" or (
            prop.domain_id is not None and prop.domain_id not in lineage
        ):
            continue
        bound = columns.get(prop.id)
        column_view: schemas.ColumnBindingView | None = None
        if bound is not None and bound.binding:
            name = str(bound.binding.get("column"))
            column = (
                next((c for c in catalog_table.columns if c.name == name), None)
                if catalog_table is not None
                else None
            )
            check: schemas.CatalogCheck = table_check
            if catalog_table is not None:
                check = "missing_column" if column is None else "ok"
            if column is not None and column.family not in binding_rules.FAMILIES.get(
                prop.datatype or "", frozenset()
            ):
                check = "type_mismatch"
            column_view = schemas.ColumnBindingView(
                element_id=bound.id,
                revision=bound.revision,
                column=name,
                column_type=column.type if column is not None else None,
                check=check,
            )
        properties.append(
            schemas.PropertyBindingView(
                property_id=prop.id,
                label=_element_name(prop),
                datatype=cast(Datatype | None, prop.datatype),
                inherited=prop.domain_id != entity.id,
                column=column_view,
            )
        )
    properties.sort(key=lambda p: (p.inherited, p.label, str(p.property_id)))
    relations: list[schemas.RelationBindingView] = []
    for relation in active:
        if relation.kind != "relation_type":
            continue
        ends: tuple[tuple[Literal["out", "in"], UUID | None, UUID | None], ...] = (
            ("out", relation.domain_id, relation.range_id),
            ("in", relation.range_id, relation.domain_id),
        )
        for direction, here, there in ends:
            other = by_id.get(there) if there is not None else None
            if here not in lineage or other is None:
                continue
            relations.append(await _relation_view(checks, relation, direction, other, own, active))
    relations.sort(key=lambda r: (r.direction != "out", r.label, str(r.relation_id)))
    return schemas.TypeBindingView(
        type_id=entity.id,
        table=table_view,
        properties=properties,
        relations=relations,
        open_change_set_ids=[
            change_set_id for change_set_id, types in pending.items() if entity.id in types
        ],
    )


async def _relation_view(
    checks: _Checks,
    relation: Element,
    direction: Literal["out", "in"],
    other: Element,
    own: Element | None,
    active: Sequence[Element],
) -> schemas.RelationBindingView:
    side = "domain_id" if direction == "out" else "range_id"
    bound = next(
        (
            e
            for e in active
            if own is not None
            and e.kind == "relation_binding"
            and e.subject_id == relation.id
            and getattr(e, side) == own.id
        ),
        None,
    )
    join_view: schemas.JoinBindingView | None = None
    if bound is not None and bound.binding:
        source = next((e for e in active if e.id == bound.domain_id), None)
        target = next((e for e in active if e.id == bound.range_id), None)
        join = bound.binding.get("join") or {}
        join_view = schemas.JoinBindingView(
            element_id=bound.id,
            revision=bound.revision,
            join=JoinBinding.model_validate(bound.binding).join,
            check=await _join_check(
                checks,
                join,
                source.binding if source is not None else None,
                target.binding if target is not None else None,
            ),
        )
    return schemas.RelationBindingView(
        relation_id=relation.id,
        label=_element_name(relation),
        direction=direction,
        other_type_id=other.id,
        other_type_label=_element_name(other),
        join=join_view,
    )


# ---------- the release in effect, for other modules ----------


@dataclass(frozen=True, slots=True)
class BoundProperty:
    property_id: UUID
    binding_id: UUID
    local_name: str
    label: str
    datatype: Datatype | None
    unit: str | None
    column: str


@dataclass(frozen=True, slots=True)
class BoundType:
    """An object type bound to a table or view; `properties` by label, then id."""

    type_id: UUID
    binding_id: UUID
    local_name: str
    label: str
    iri: str | None
    data_source_id: UUID
    schema: str
    table: str
    key_columns: tuple[str, ...]
    properties: tuple[BoundProperty, ...]


@dataclass(frozen=True, slots=True)
class ForeignKeyHop:
    """`side = source`: the source table's `columns` refer to the target table's
    `references`; `side = target`: the target table's `columns` refer to the source's."""

    side: Literal["source", "target"]
    columns: tuple[str, ...]
    references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LinkTableHop:
    """A link table in the data source of both ends; its column groups match their keys."""

    schema: str
    table: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundRelation:
    """A relation bound between the tables of two bound types, from `source_type_id` (its
    domain side) to `target_type_id`. `inverse_*` name the inverse relation, if any."""

    relation_id: UUID
    binding_id: UUID
    local_name: str
    label: str
    source_type_id: UUID
    target_type_id: UUID
    join: ForeignKeyHop | LinkTableHop
    inverse_id: UUID | None
    inverse_label: str | None


@dataclass(frozen=True, slots=True)
class BoundModel:
    """The bindings of the release an ontology has in effect (spec 003, 6.4 and 7)."""

    ontology_id: UUID
    release_id: UUID
    version: int
    types: tuple[BoundType, ...]
    relations: tuple[BoundRelation, ...]

    def type(self, type_id: UUID) -> BoundType | None:
        return next((bound for bound in self.types if bound.type_id == type_id), None)


@dataclass(frozen=True, slots=True)
class ReleasedOntology:
    """The semantic part of the release an ontology has in effect: its active elements as
    published, without bindings, and which object types are bound to data in it. The elements
    are copies made for the caller."""

    ontology_id: UUID
    key: str
    name: str
    description: str | None
    release_id: UUID
    version: int
    published_at: datetime
    elements: tuple[schemas.ElementCopy, ...]
    bound_type_ids: frozenset[UUID]


async def _release_in_effect(
    db: AsyncSession, ontology: UUID | str
) -> tuple[Ontology, Release] | None:
    """The ontology (by id, by its id as text, or by key) and its active release. The
    release's Turtle, which can be megabytes, is not read."""
    if isinstance(ontology, str):
        ontology = rules.parse_id(ontology) or ontology
    by_id = isinstance(ontology, UUID)
    condition = Ontology.id == ontology if by_id else Ontology.key == ontology
    row = (
        await db.execute(
            select(Ontology, Release)
            .join(Release, Release.id == Ontology.active_release_id)
            .where(condition)
            .options(defer(Release.turtle))
        )
    ).first()
    return (row[0], row[1]) if row is not None else None


def _hop(join: Mapping[str, Any]) -> ForeignKeyHop | LinkTableHop:
    if join.get("kind") == "link_table":
        return LinkTableHop(
            schema=str(join["schema"]),
            table=str(join["table"]),
            source_columns=tuple(join["sourceColumns"]),
            target_columns=tuple(join["targetColumns"]),
        )
    return ForeignKeyHop(
        side="target" if join.get("side") == "target" else "source",
        columns=tuple(join["columns"]),
        references=tuple(join["references"]),
    )


def _model(release: Release) -> BoundModel:
    rows = {str(row["id"]): row for row in release.snapshot}
    by_parent: dict[str, list[BoundProperty]] = {}
    for row in rows.values():
        prop = rows.get(str(row.get("subjectId")))
        if row["kind"] != "property_binding" or prop is None:
            continue
        by_parent.setdefault(str(row["parentId"]), []).append(
            BoundProperty(
                property_id=UUID(str(prop["id"])),
                binding_id=UUID(str(row["id"])),
                local_name=str(prop.get("localName") or ""),
                label=_label(prop),
                datatype=prop.get("datatype"),
                unit=prop.get("unit"),
                column=str(row["binding"]["column"]),
            )
        )
    types: list[BoundType] = []
    for row in rows.values():
        subject = rows.get(str(row.get("subjectId")))
        if row["kind"] != "type_binding" or subject is None:
            continue
        binding = row["binding"]
        properties = sorted(
            by_parent.get(str(row["id"]), []), key=lambda p: (p.label, str(p.property_id))
        )
        types.append(
            BoundType(
                type_id=UUID(str(subject["id"])),
                binding_id=UUID(str(row["id"])),
                local_name=str(subject.get("localName") or ""),
                label=_label(subject),
                iri=subject.get("iri"),
                data_source_id=UUID(str(binding["dataSourceId"])),
                schema=str(binding["schema"]),
                table=str(binding["table"]),
                key_columns=tuple(binding["keyColumns"]),
                properties=tuple(properties),
            )
        )
    relations: list[BoundRelation] = []
    for row in rows.values():
        relation = rows.get(str(row.get("subjectId")))
        source = rows.get(str(row.get("domainId")))
        target = rows.get(str(row.get("rangeId")))
        if row["kind"] != "relation_binding" or relation is None:
            continue
        if source is None or target is None:
            continue
        inverse = rows.get(str(relation.get("inverseId"))) if relation.get("inverseId") else None
        relations.append(
            BoundRelation(
                relation_id=UUID(str(relation["id"])),
                binding_id=UUID(str(row["id"])),
                local_name=str(relation.get("localName") or ""),
                label=_label(relation),
                source_type_id=UUID(str(source["subjectId"])),
                target_type_id=UUID(str(target["subjectId"])),
                join=_hop(row["binding"]["join"]),
                inverse_id=UUID(str(inverse["id"])) if inverse is not None else None,
                inverse_label=_label(inverse) if inverse is not None else None,
            )
        )
    return BoundModel(
        ontology_id=release.ontology_id,
        release_id=release.id,
        version=release.version,
        types=tuple(sorted(types, key=lambda t: (t.label, str(t.type_id)))),
        relations=tuple(sorted(relations, key=lambda r: (r.label, str(r.binding_id)))),
    )


async def bound_model(db: AsyncSession, ontology: UUID | str) -> BoundModel | None:
    """The bindings of the release in effect of the ontology (by id or by key); None when it
    has no release in effect (or does not exist). A release published before M3 has no
    bindings: its model is empty."""
    found = await _release_in_effect(db, ontology)
    return _model(found[1]) if found is not None else None


# Snapshots of releases published before M2 lack the later fields.
_SNAPSHOT_DEFAULTS: dict[str, Any] = {
    "explicitIri": False,
    "synonyms": [],
    "inverseId": None,
    "unit": None,
    "required": False,
    "multiple": False,
    "autoShape": True,
    "rules": None,
    "turtle": None,
    "subjectId": None,
    "flags": [],
}


async def released_ontology(db: AsyncSession, ontology: UUID | str) -> ReleasedOntology | None:
    """The ontology (by id or by key) as its release in effect has it; None when it has no
    release in effect or does not exist."""
    found = await _release_in_effect(db, ontology)
    if found is None:
        return None
    row, release = found
    elements = tuple(
        schemas.ElementCopy.model_validate({**_SNAPSHOT_DEFAULTS, **element})
        for element in release.snapshot
        if element["kind"] in SEMANTIC_KINDS
    )
    bound = frozenset(
        UUID(str(element["subjectId"]))
        for element in release.snapshot
        if element["kind"] == "type_binding" and element.get("subjectId")
    )
    return ReleasedOntology(
        ontology_id=row.id,
        key=row.key,
        name=row.name,
        description=row.description,
        release_id=release.id,
        version=release.version,
        published_at=release.created_at,
        elements=elements,
        bound_type_ids=bound,
    )


# ---------- for the connectors module ----------


async def table_usage(db: AsyncSession, data_source_id: UUID) -> list[TableUsage]:
    """Object types bound to tables of the data source, in working versions or in the release
    each ontology has in effect, by schema, table and type."""
    source = str(data_source_id)
    found: dict[tuple[str, str, UUID], dict[str, Any]] = {}

    bound = await db.execute(
        select(Element.subject_id, Element.binding).where(
            Element.kind == "type_binding",
            Element.status == "active",
            Element.binding["dataSourceId"].astext == source,
        )
    )
    working = [(subject_id, binding) for subject_id, binding in bound if subject_id and binding]
    labels: dict[UUID, str] = {}
    if working:
        subjects = await db.scalars(
            select(Element).where(Element.id.in_({subject_id for subject_id, _ in working}))
        )
        labels = {
            element.id: rules.display_label(element.label_zh, element.label_en, element.local_name)
            for element in subjects
        }
    for subject_id, binding in working:
        key = (str(binding["schema"]), str(binding["table"]), subject_id)
        entry = found.setdefault(key, {"label": labels.get(subject_id, ""), "working": False})
        entry["working"] = True

    snapshots = await db.scalars(
        select(Release.snapshot)
        .join(Ontology, Ontology.active_release_id == Release.id)
        .where(
            Release.snapshot.contains(
                [{"kind": "type_binding", "binding": {"dataSourceId": source}}]
            )
        )
    )
    for snapshot in snapshots:
        by_id = {str(row["id"]): row for row in snapshot}
        for row in snapshot:
            binding = row.get("binding") or {}
            if row.get("kind") != "type_binding" or binding.get("dataSourceId") != source:
                continue
            subject = by_id.get(str(row.get("subjectId")))
            subject_id = UUID(str(row["subjectId"]))
            key = (str(binding["schema"]), str(binding["table"]), subject_id)
            entry = found.setdefault(
                key, {"label": _label(subject) if subject else "", "working": False}
            )
            entry["released"] = True

    return [
        TableUsage(
            schema=schema,
            table=table,
            type_id=type_id,
            type_label=entry["label"],
            in_working_version=bool(entry.get("working")),
            in_active_release=bool(entry.get("released")),
        )
        for (schema, table, type_id), entry in sorted(found.items(), key=lambda item: item[0][:2])
    ]
