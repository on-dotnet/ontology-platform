"""Plan a read using the active bindings and detached catalog metadata."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.schemas import CatalogColumn, DataSourceRef
from ontology_platform.modules.connectors.statements import (
    ColumnRef,
    Condition,
    Join,
    SortKey,
    TableRef,
    Value,
)
from ontology_platform.modules.ontology.bindings import (
    BoundModel,
    BoundProperty,
    BoundRelation,
    BoundType,
    ForeignKeyHop,
)
from ontology_platform.modules.query import errors, schemas, values


def bound_type(model: BoundModel, type_id: UUID) -> BoundType:
    bound = model.type(type_id)
    if bound is None:
        raise AppError(409, "query.type_not_bound", "The type is not bound in the active release.")
    return bound


@dataclass
class Table:
    bound: BoundType
    source_name: str
    columns: dict[str, CatalogColumn]
    problem: schemas.TypeProblem | None

    @property
    def ref(self) -> TableRef:
        return TableRef(self.bound.schema, self.bound.table)

    def require_available(self) -> None:
        if self.problem == "source_disabled":
            raise errors.source_disabled()
        if self.problem is not None:
            raise errors.source_mismatch()

    def projection(self) -> tuple[ColumnRef, ...]:
        names = [*self.bound.key_columns, *(prop.column for prop in self.bound.properties)]
        return tuple(ColumnRef(name) for name in dict.fromkeys(names))

    def key_specs(self) -> list[CatalogColumn]:
        return [self.columns[name] for name in self.bound.key_columns]

    def properties(self) -> list[schemas.ObjectProperty]:
        result = []
        for prop in self.bound.properties:
            if prop.datatype is None:
                continue
            column = self.columns.get(prop.column)
            result.append(
                schemas.ObjectProperty(
                    property_id=prop.property_id,
                    label=prop.label,
                    datatype=prop.datatype,
                    unit=prop.unit,
                    ops=values.ops(prop.datatype, column.family) if column else [],
                )
            )
        return result


class Catalog:
    """Look up each source and table once per request, including self-relations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.sources: dict[UUID, DataSourceRef | None] = {}
        self.columns: dict[tuple[UUID, TableRef], dict[str, CatalogColumn]] = {}

    async def table_columns(self, source_id: UUID, ref: TableRef) -> dict[str, CatalogColumn]:
        if (source_id, ref) not in self.columns:
            table = await connectors.get_catalog_table(self.db, source_id, ref)
            self.columns[source_id, ref] = {c.name: c for c in table.columns} if table else {}
        return self.columns[source_id, ref]

    async def table(self, bound: BoundType) -> Table:
        source_id = bound.data_source_id
        if source_id not in self.sources:
            self.sources[source_id] = await connectors.get_data_source_ref(self.db, source_id)
        source = self.sources[source_id]
        columns = await self.table_columns(source_id, TableRef(bound.schema, bound.table))
        problem: schemas.TypeProblem | None = None
        if source is None or source.status != "active" or not source.has_credential:
            problem = "source_disabled"
        elif (
            not bound.key_columns
            or any(
                name not in columns or columns[name].family == "other" for name in bound.key_columns
            )
            or any(
                prop.datatype is None
                or prop.column not in columns
                or not values.ops(prop.datatype, columns[prop.column].family)
                for prop in bound.properties
            )
        ):
            problem = "source_mismatch"
        return Table(bound, source.name if source else "", columns, problem)


def relations(
    model: BoundModel, origin: UUID | None = None
) -> dict[UUID, list[tuple[schemas.ObjectRelation, BoundRelation]]]:
    types = {bound.type_id: bound for bound in model.types}
    result: dict[UUID, list[tuple[schemas.ObjectRelation, BoundRelation]]] = {}
    for relation in model.relations:
        source = types[relation.source_type_id]
        target = types[relation.target_type_id]
        if origin is None or origin == source.type_id:
            outward = schemas.ObjectRelation(
                relation_id=relation.relation_id,
                label=relation.label,
                direction="out",
                other_type_id=target.type_id,
                other_type_label=target.label,
            )
            result.setdefault(source.type_id, []).append((outward, relation))
        if origin is None or origin == target.type_id:
            inward = schemas.ObjectRelation(
                relation_id=relation.inverse_id or relation.relation_id,
                label=relation.inverse_label or relation.label,
                direction="in",
                other_type_id=source.type_id,
                other_type_label=source.label,
            )
            result.setdefault(target.type_id, []).append((inward, relation))
    return result


def _property(properties: dict[UUID, BoundProperty], property_id: UUID) -> BoundProperty:
    prop = properties.get(property_id)
    if prop is None:
        raise AppError(422, "query.invalid_filter", "The filter is invalid.")
    return prop


def resolve_relation(
    model: BoundModel, origin: UUID, relation_id: UUID, direction: schemas.Direction
) -> tuple[BoundType, BoundRelation]:
    matches = [
        (info, relation)
        for info, relation in relations(model, origin).get(origin, [])
        if (info.relation_id, info.direction) == (relation_id, direction)
    ]
    if not matches:
        raise AppError(409, "query.type_not_bound", "The requested relation is not bound here.")
    if len(matches) > 1:
        raise AppError(
            409, "query.source_mismatch", "The requested relation has ambiguous bindings."
        )
    info, relation = matches[0]
    return bound_type(model, info.other_type_id), relation


def search_terms(
    table: Table, body: schemas.ObjectSearch
) -> tuple[tuple[Condition, ...], tuple[SortKey, ...]]:
    properties = {prop.property_id: prop for prop in table.bound.properties}
    where = []
    for item in body.filters:
        prop = _property(properties, item.property_id)
        if prop.datatype is None:
            raise errors.source_mismatch()
        where.append(values.condition(item, table.columns[prop.column], prop.datatype))
    order: dict[str, SortKey] = {}
    for sort in body.sort:
        name = _property(properties, sort.property_id).column
        order.setdefault(name, SortKey(ColumnRef(name), descending=sort.direction == "desc"))
    for name in table.bound.key_columns:
        order.setdefault(name, SortKey(ColumnRef(name)))
    return tuple(where), tuple(order.values())


def key_conditions(names: Sequence[str], key: Sequence[Value]) -> tuple[Condition, ...]:
    return tuple(
        Condition(ColumnRef(name), "eq", value) for name, value in zip(names, key, strict=True)
    )


def hop_join(
    origin: Table,
    target: Table,
    relation: BoundRelation,
    direction: schemas.Direction,
) -> tuple[Join, tuple[str, ...]]:
    hop = relation.join
    forward = direction == "out"
    if isinstance(hop, ForeignKeyHop):
        target_holds_fk = (hop.side == "target") == forward
        main, joined = (
            (hop.columns, hop.references) if target_holds_fk else (hop.references, hop.columns)
        )
        join = Join(origin.ref, tuple(zip(main, joined, strict=True)))
        return join, origin.bound.key_columns
    origin_columns, target_columns = (
        (hop.source_columns, hop.target_columns)
        if forward
        else (hop.target_columns, hop.source_columns)
    )
    join = Join(
        TableRef(hop.schema, hop.table),
        tuple(zip(target.bound.key_columns, target_columns, strict=True)),
    )
    return join, origin_columns


def joined_key(
    origin: Table, parts: tuple[Value, ...], specs: Sequence[CatalogColumn]
) -> tuple[Condition, ...]:
    conditions = []
    for key_col, value, col in zip(origin.key_specs(), parts, specs, strict=True):
        if (col.family, col.type) != (key_col.family, key_col.type):
            # Link-table parameters are bound using their own columns. A lossy conversion
            # could associate two distinct starting objects with the same set of links.
            encoded = values.string_value(value)
            try:
                value = values.parse_value(encoded, col)
            except ValueError:
                raise errors.source_mismatch() from None
            if values.string_value(value) != encoded:
                raise errors.source_mismatch()
        conditions.append(Condition(ColumnRef(col.name, "joined"), "eq", value))
    return tuple(conditions)
