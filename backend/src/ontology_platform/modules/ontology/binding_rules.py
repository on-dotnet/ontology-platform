"""Data bindings: their shape, their checks and the type compatibility table (spec 003, 6.2).

Proposals, reviewer edits, merges and publishing share these rules. The checks work on `Node`s,
a plain view of elements and of the items of a change set as they would leave the working
version, so that one rule serves the database rows, the change items and the snapshots alike.

Only proposals and edits compare a binding with the cached catalog (`catalog_problems`): the
cache can be out of date by the time a change set is merged or published.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.schemas import CatalogTableCopy
from ontology_platform.modules.connectors.statements import TableRef
from ontology_platform.modules.ontology.models import BINDING_KINDS, Element
from ontology_platform.modules.ontology.schemas import (
    Binding,
    ElementFields,
    ForeignKeyJoin,
    JoinBinding,
    LinkTableJoin,
    TableBinding,
)

INVALID = "binding.invalid"
DUPLICATE = "binding.duplicate"
TYPE_MISMATCH = "binding.type_mismatch"
CROSS_SOURCE = "binding.cross_source"
STATUS = {INVALID: 422, DUPLICATE: 409, TYPE_MISMATCH: 422, CROSS_SOURCE: 422}

# What each kind binds to (`Binding.target`).
TARGETS = {"type_binding": "table", "property_binding": "column", "relation_binding": "join"}
# The references each binding kind has; all of them are required.
REFS: dict[str, tuple[str, ...]] = {
    "type_binding": ("subject_ref",),
    "property_binding": ("subject_ref", "parent_ref"),
    "relation_binding": ("subject_ref", "domain_ref", "range_ref"),
}
# The kinds each reference of a binding points at.
REF_TARGETS: dict[tuple[str, str], tuple[str, ...]] = {
    ("type_binding", "subject_ref"): ("entity_type",),
    ("property_binding", "subject_ref"): ("property",),
    ("property_binding", "parent_ref"): ("type_binding",),
    ("relation_binding", "subject_ref"): ("relation_type",),
    ("relation_binding", "domain_ref"): ("type_binding",),
    ("relation_binding", "range_ref"): ("type_binding",),
}
_SUBJECT_KINDS = {
    "type_binding": "entity_type",
    "property_binding": "property",
    "relation_binding": "relation_type",
}
# The column families a property of each datatype can be bound to (spec 003, 5.5): only those
# that compare without converting the column.
FAMILIES: dict[str, frozenset[str]] = {
    "string": frozenset({"string", "opaque"}),
    "integer": frozenset({"integer"}),
    "decimal": frozenset({"integer", "decimal"}),
    "boolean": frozenset({"boolean"}),
    "date": frozenset({"date"}),
    "dateTime": frozenset({"date", "dateTime"}),
}
# Families a key column cannot have: the platform cannot compare or page by them.
_NO_KEY_FAMILIES = frozenset({"other"})


@dataclass(frozen=True, slots=True)
class Problem:
    code: str
    message: str


# ---------- shape: no lookups ----------


def _unique(columns: Iterable[str]) -> bool:
    listed = list(columns)
    return len(set(listed)) == len(listed)


def _value_problems(binding: Binding) -> list[str]:
    if isinstance(binding, TableBinding) and not _unique(binding.key_columns):
        return ["keyColumns has a column twice"]
    if isinstance(binding, JoinBinding):
        join = binding.join
        if isinstance(join, ForeignKeyJoin):
            if len(join.columns) != len(join.references):
                return ["a foreign key needs as many columns as references"]
            if not _unique(join.columns) or not _unique(join.references):
                return ["a foreign key has a column twice"]
        elif not _unique(join.source_columns) or not _unique(join.target_columns):
            return ["a link table has a column twice"]
    return []


def shape_problems(
    kind: str,
    op: str,
    fields: ElementFields,
    target_binding: Mapping[str, Any] | None,
) -> list[str]:
    """Problems with a binding item's fields that need no lookups (`create`, `update`,
    `restore`; a delete carries no fields). Only `binding` changes on an existing binding, and
    of a type binding only the key columns: anything else is a delete and a new binding."""
    given = fields.model_fields_set
    problems: list[str] = []
    if op == "create":
        problems.extend(
            f"{to_camel(name)} is required" for name in REFS[kind] if getattr(fields, name) is None
        )
        if fields.binding is None:
            problems.append("binding is required")
    else:
        if any(name in given for name in REFS[kind]):
            problems.append(
                "a binding cannot move to other elements; delete it and create a new one"
            )
        if "binding" in given and fields.binding is None:
            problems.append("binding is required")
    binding = fields.binding
    if binding is None:
        return problems
    if binding.target != TARGETS[kind]:
        problems.append(f"a {kind} binds to a {TARGETS[kind]}")
        return problems
    problems.extend(_value_problems(binding))
    if op != "create" and isinstance(binding, TableBinding) and target_binding is not None:
        moved = (
            str(binding.data_source_id) != str(target_binding.get("dataSourceId"))
            or binding.schema_name != target_binding.get("schema")
            or binding.table != target_binding.get("table")
        )
        if moved:
            problems.append(
                "only the key columns of a type binding can change; to bind another table,"
                " delete the binding and create a new one"
            )
    return problems


def stored(binding: Binding) -> dict[str, Any]:
    """A binding as `elements.binding` and the snapshots hold it (camelCase JSON)."""
    data: dict[str, Any] = binding.model_dump(mode="json", by_alias=True)
    return data


# ---------- nodes: elements and items as the change leaves them ----------


@dataclass(frozen=True, slots=True)
class Node:
    """What the binding checks need of an element or of an item. `key` is the element id as a
    string, or `ref:<temp_ref>` for an item that creates one; references use the same keys."""

    key: str
    kind: str
    active: bool
    parent: str | None = None
    domain: str | None = None
    range: str | None = None
    subject: str | None = None
    datatype: str | None = None
    binding: Mapping[str, Any] | None = None


def ref_key(value: str | UUID | None) -> str | None:
    """The node key of a reference: an element id or the temp_ref of an item."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    try:
        return str(UUID(value))
    except ValueError:
        return f"ref:{value}"


def element_node(element: Element) -> Node:
    return Node(
        key=str(element.id),
        kind=element.kind,
        active=element.status == "active",
        parent=ref_key(element.parent_id),
        domain=ref_key(element.domain_id),
        range=ref_key(element.range_id),
        subject=ref_key(element.subject_id),
        datatype=element.datatype,
        binding=element.binding,
    )


def row_node(row: Mapping[str, Any]) -> Node:
    """A node of a snapshot row (camelCase JSON of an element, always active)."""
    return Node(
        key=str(row["id"]),
        kind=str(row["kind"]),
        active=True,
        parent=ref_key(row.get("parentId")),
        domain=ref_key(row.get("domainId")),
        range=ref_key(row.get("rangeId")),
        subject=ref_key(row.get("subjectId")),
        datatype=row.get("datatype"),
        binding=row.get("binding"),
    )


_REF_ATTRS = {
    "parent_ref": "parent",
    "domain_ref": "domain",
    "range_ref": "range",
    "subject_ref": "subject",
}


def applied(
    node: Node | None,
    *,
    op: str,
    kind: str,
    key: str,
    fields: ElementFields,
) -> Node:
    """The node after an item: a new one for a create, `node` changed for the others."""
    given = fields.model_fields_set
    if op == "create" or node is None:
        node = Node(key=key, kind=kind, active=True)
    if op == "delete":
        return replace(node, active=False)
    changes: dict[str, Any] = {"active": True}
    for name, attr in _REF_ATTRS.items():
        if name in given:
            changes[attr] = ref_key(getattr(fields, name))
    if "datatype" in given:
        changes["datatype"] = fields.datatype
    if "binding" in given:
        changes["binding"] = stored(fields.binding) if fields.binding is not None else None
    return replace(node, **changes)


@dataclass(frozen=True, slots=True)
class Proposed:
    """An item of a change set: what `change_set_nodes` and the checks read of it."""

    op: str
    kind: str
    target_id: UUID | None
    temp_ref: str | None
    fields: ElementFields


def item_key(item: Proposed, position: int) -> str:
    if item.target_id is not None:
        return str(item.target_id)
    if item.temp_ref is not None:
        return f"ref:{item.temp_ref}"
    return f"item:{position}"


def change_set_nodes(elements: Iterable[Element], items: Iterable[Proposed]) -> dict[str, Node]:
    """The elements as the items would leave them, deletes included."""
    nodes = {str(element.id): element_node(element) for element in elements}
    for position, item in enumerate(items):
        key = item_key(item, position)
        nodes[key] = applied(
            nodes.get(key), op=item.op, kind=item.kind, key=key, fields=item.fields
        )
    return nodes


def binding_impacts(
    elements: Sequence[Element], items: Sequence[Proposed], *, target_ids: set[UUID] | None = None
) -> list[tuple[Element, Problem]]:
    """Existing valid bindings made invalid by items aimed at other elements."""
    before = {str(element.id): element_node(element) for element in elements}
    after = change_set_nodes(elements, items)
    targets = (
        target_ids
        if target_ids is not None
        else {item.target_id for item in items if item.target_id is not None}
    )
    found: list[tuple[Element, Problem]] = []
    for element in elements:
        if element.status != "active" or element.kind not in BINDING_KINDS or element.id in targets:
            continue
        key = str(element.id)
        if node_problems(before[key], before):
            continue
        problems = node_problems(after[key], after)
        if problems:
            found.append((element, problems[0]))
    return found


# ---------- checks against the other elements ----------


def _active(nodes: Mapping[str, Node], key: str | None, kind: str) -> Node | None:
    node = nodes.get(key) if key is not None else None
    return node if node is not None and node.kind == kind and node.active else None


def _ancestors(nodes: Mapping[str, Node], key: str) -> set[str]:
    """The object type and the types above it."""
    found: set[str] = set()
    current: str | None = key
    while current is not None and current not in found:
        found.add(current)
        node = nodes.get(current)
        current = node.parent if node is not None else None
    return found


def _fits(nodes: Mapping[str, Node], wanted: str | None, bound: str | None) -> bool:
    """Whether a table of type `bound` can stand for `wanted` (a domain or range): the same
    type or one of its subtypes. No domain or range fits any type."""
    return wanted is None or (bound is not None and wanted in _ancestors(nodes, bound))


def _same_binding(node: Node, other: Node) -> bool:
    if other.key == node.key or other.kind != node.kind or not other.active:
        return False
    if other.subject != node.subject:
        return False
    if node.kind == "property_binding":
        return other.parent == node.parent
    if node.kind == "relation_binding":
        return (other.domain, other.range) == (node.domain, node.range)
    return True


def node_problems(node: Node, nodes: Mapping[str, Node]) -> list[Problem]:
    """What is wrong with an active binding among `nodes` (which it need not be part of).
    Only rules that need no catalog: merges and the publish checks use these."""
    if node.kind not in BINDING_KINDS or not node.active:
        return []
    subject = _active(nodes, node.subject, _SUBJECT_KINDS[node.kind])
    if subject is None:
        return [Problem(INVALID, "the bound element is missing or not active")]
    binding = node.binding or {}
    if binding.get("target") != TARGETS[node.kind]:
        return [Problem(INVALID, f"a {node.kind} binds to a {TARGETS[node.kind]}")]
    problems: list[Problem] = []
    if node.kind == "property_binding":
        parent = _active(nodes, node.parent, "type_binding")
        if parent is None:
            return [Problem(INVALID, "the type binding is missing or not active")]
        if not _fits(nodes, subject.domain, parent.subject):
            problems.append(
                Problem(INVALID, "the property belongs to neither the bound type nor its parents")
            )
    elif node.kind == "relation_binding":
        source = _active(nodes, node.domain, "type_binding")
        target = _active(nodes, node.range, "type_binding")
        if source is None or target is None:
            return [Problem(INVALID, "a type binding of the relation is missing or not active")]
        if not _fits(nodes, subject.domain, source.subject) or not _fits(
            nodes, subject.range, target.subject
        ):
            problems.append(
                Problem(INVALID, "the bound types do not fit the relation's domain and range")
            )
        source_table, target_table = source.binding or {}, target.binding or {}
        if source_table.get("dataSourceId") != target_table.get("dataSourceId"):
            problems.append(
                Problem(CROSS_SOURCE, "both ends of a relation must be in one data source")
            )
        join = binding.get("join") or {}
        if join.get("kind") == "foreign_key":
            if len(join.get("columns") or []) != len(join.get("references") or []):
                problems.append(
                    Problem(INVALID, "a foreign key needs as many columns as references")
                )
        elif len(join.get("sourceColumns") or []) != len(
            source_table.get("keyColumns") or []
        ) or len(join.get("targetColumns") or []) != len(target_table.get("keyColumns") or []):
            problems.append(
                Problem(INVALID, "the link table's columns must match the key columns of both ends")
            )
    elif not _unique(binding.get("keyColumns") or []):
        problems.append(Problem(INVALID, "keyColumns has a column twice"))
    if any(_same_binding(node, other) for other in nodes.values()):
        problems.append(Problem(DUPLICATE, "this element already has an active binding"))
    return problems


# ---------- checks against the data source and its cached catalog ----------


async def data_source_problem(db: AsyncSession, data_source_id: object) -> Problem | None:
    """A type binding needs a data source that exists and is not archived."""
    try:
        source_id = UUID(str(data_source_id))
    except ValueError:
        return Problem(INVALID, "the data source does not exist")
    source = await connectors.get_data_source_ref(db, source_id)
    if source is None:
        return Problem(INVALID, "the data source does not exist")
    if source.status != "active":
        return Problem(INVALID, "the data source is archived")
    return None


class _Catalog:
    """Cached catalog tables, each read once."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._tables: dict[tuple[str, str, str], CatalogTableCopy | None] = {}

    async def table(self, source: object, schema: object, name: object) -> CatalogTableCopy | None:
        key = (str(source), str(schema), str(name))
        if key not in self._tables:
            try:
                source_id = UUID(key[0])
            except ValueError:
                self._tables[key] = None
            else:
                self._tables[key] = await connectors.get_catalog_table(
                    self._db, source_id, TableRef(schema=key[1], name=key[2])
                )
        return self._tables[key]


def _missing(table: CatalogTableCopy, columns: Iterable[str]) -> list[str]:
    names = {column.name for column in table.columns}
    return [column for column in columns if column not in names]


def _where(table: CatalogTableCopy) -> str:
    return f"{table.schema_name}.{table.name}"


async def catalog_problems(
    db: AsyncSession,
    node: Node,
    nodes: Mapping[str, Node],
    catalog: _Catalog | None = None,
) -> list[Problem]:
    """Whether the tables and columns a binding names are in the cached catalog, and whether a
    column's type fits the property it is bound to. Run after `node_problems` found nothing."""
    catalog = catalog or _Catalog(db)
    binding = node.binding or {}
    if node.kind == "type_binding":
        problem = await data_source_problem(db, binding.get("dataSourceId"))
        if problem is not None:
            return [problem]
        table = await catalog.table(
            binding.get("dataSourceId"), binding.get("schema"), binding.get("table")
        )
        if table is None:
            return [Problem(INVALID, "the catalog of the data source has no such table")]
        keys = list(binding.get("keyColumns") or [])
        missing = _missing(table, keys)
        if missing:
            return [Problem(INVALID, f"{_where(table)} has no column {', '.join(missing)}")]
        families = {column.name: column.family for column in table.columns}
        if any(families[key] in _NO_KEY_FAMILIES for key in keys):
            return [Problem(INVALID, "a key column must be of a type the platform can compare")]
        return []
    if node.kind == "property_binding":
        parent = nodes[node.parent or ""].binding or {}
        table = await catalog.table(
            parent.get("dataSourceId"), parent.get("schema"), parent.get("table")
        )
        if table is None:
            return [Problem(INVALID, "the catalog of the data source has no such table")]
        name = binding.get("column")
        column = next((c for c in table.columns if c.name == name), None)
        if column is None:
            return [Problem(INVALID, f"{_where(table)} has no column {name}")]
        datatype = nodes[node.subject or ""].datatype
        if column.family not in FAMILIES.get(datatype or "", frozenset()):
            return [
                Problem(
                    TYPE_MISMATCH,
                    f"a {column.type} column cannot hold a property of type {datatype}",
                )
            ]
        return []
    if node.kind != "relation_binding":
        return []
    source = nodes[node.domain or ""].binding or {}
    target = nodes[node.range or ""].binding or {}
    source_table = await catalog.table(
        source.get("dataSourceId"), source.get("schema"), source.get("table")
    )
    target_table = await catalog.table(
        target.get("dataSourceId"), target.get("schema"), target.get("table")
    )
    if source_table is None or target_table is None:
        return [Problem(INVALID, "the catalog of the data source has no such table")]
    join = JoinBinding.model_validate(binding).join
    if isinstance(join, LinkTableJoin):
        link = await catalog.table(source.get("dataSourceId"), join.schema_name, join.table)
        if link is None:
            return [Problem(INVALID, "the catalog of the data source has no such link table")]
        sides = [(link, [*join.source_columns, *join.target_columns])]
    elif join.side == "source":
        sides = [(source_table, join.columns), (target_table, join.references)]
    else:
        sides = [(target_table, join.columns), (source_table, join.references)]
    for table, columns in sides:
        missing = _missing(table, columns)
        if missing:
            return [Problem(INVALID, f"{_where(table)} has no column {', '.join(missing)}")]
    return []


async def proposal_problems(
    db: AsyncSession,
    elements: Iterable[Element],
    items: list[Proposed],
    *,
    only: int | None = None,
) -> list[tuple[int, Problem]]:
    """(item position, problem) for the binding items of a change set: checked among the other
    elements and items as the change set leaves them, and against the cached catalog. `only`
    restricts the checks to one item (a reviewer's edit)."""
    nodes = change_set_nodes(elements, items)
    catalog = _Catalog(db)
    found: list[tuple[int, Problem]] = []
    for position, item in enumerate(items):
        if item.kind not in BINDING_KINDS or item.op == "delete":
            continue
        if only is not None and position != only:
            continue
        node = nodes[item_key(item, position)]
        problems = node_problems(node, nodes) or await catalog_problems(db, node, nodes, catalog)
        found.extend((position, problem) for problem in problems)
    return found


@dataclass(frozen=True, slots=True)
class Sibling:
    """An item of the change set a reviewer edits, with its effective fields."""

    id: UUID
    rejected: bool
    item: Proposed


async def edit_problems(
    db: AsyncSession,
    elements: Iterable[Element],
    siblings: Sequence[Sibling],
    item_id: UUID,
    fields: ElementFields,
) -> list[Problem]:
    """What is wrong with a binding item once a reviewer gives it `fields`, among the other
    items of its change set. Rejected items do not take part: the change set leaves the
    working version without them, whatever the reviewer edits here."""
    taking_part = [s for s in siblings if s.id == item_id or not s.rejected]
    items = [replace(s.item, fields=fields) if s.id == item_id else s.item for s in taking_part]
    position = next(i for i, s in enumerate(taking_part) if s.id == item_id)
    found = await proposal_problems(db, elements, items, only=position)
    return [problem for _, problem in found]
