"""Follow the bound relations and retain a witness for each complete path answer."""

from dataclasses import dataclass, field
from itertools import batched, islice
from uuid import UUID

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors import config
from ontology_platform.modules.connectors.statements import ColumnRef, SelectQuery, SortKey
from ontology_platform.modules.query import cursor, errors, planner, rows, schemas
from ontology_platform.modules.query.scan import Execution, check_size, object_pages, step


@dataclass
class Level:
    table: planner.Table
    objects: dict[str, schemas.ObjectRow]
    step: schemas.Step
    # Insertion order retains the first prefix reaching each object.
    prefixes: dict[str, tuple[str, ...]]
    children: dict[str, dict[str, None]] = field(default_factory=dict)


async def _advance(
    execution: Execution, origin: Level, hop: schemas.PathHop, maximum: int
) -> Level:
    relation = planner.resolve_relation(
        execution.model, origin.table.bound.type_id, hop.relation_id, hop.direction
    )
    target = await execution.catalog.table(relation.other)
    target.require_available()
    where, order = planner.primary_key_terms(target, hop.filters)
    join, names = planner.hop_join(origin.table, target, relation.relation, relation.direction)
    joined = await execution.catalog.table_columns(target.bound.data_source_id, join.table)
    try:
        specs = [joined[name] for name in names]
    except KeyError:
        raise errors.source_mismatch() from None
    sources = tuple(ColumnRef(name, "joined") for name in names)
    columns = target.projection() + sources
    order += tuple(SortKey(col) for col in sources)
    start = execution.budget.statements
    key_specs = origin.table.key_specs()
    batch_size = schemas.IN_VALUES_MAX if len(key_specs) == 1 else 1
    objects: dict[str, schemas.ObjectRow] = {}
    pairs = 0
    for batch in batched(origin.prefixes, batch_size, strict=False):
        batch_keys = set(batch)
        parts = [cursor.decode_key(key, key_specs) for key in batch]
        query = SelectQuery(
            data_source_id=target.bound.data_source_id,
            table=target.ref,
            columns=columns,
            join=join,
            where=where + planner.joined_batch(origin.table, parts, specs),
            order_by=order,
            limit=config.current().query_max_rows,
        )
        async for page in execution.pages(query):
            for key, row in rows.joined_objects(target, query, page):
                if key not in batch_keys:
                    raise errors.source_mismatch()
                children = origin.children.setdefault(key, {})
                if row.key not in children:
                    children[row.key] = None
                    pairs += 1
                    # Every distinct target occurs in at least one distinct pair.
                    check_size(pairs, maximum)
                    objects.setdefault(row.key, row)
    prefixes: dict[str, tuple[str, ...]] = {}
    for key, prefix in origin.prefixes.items():
        for child in origin.children.get(key, {}):
            prefixes.setdefault(child, (*prefix, child))
    return Level(
        target,
        objects,
        step(target, hop.filters, execution.budget.statements - start, len(objects)),
        prefixes,
    )


@dataclass
class Walk:
    levels: list[Level]
    target: int
    paths: dict[str, tuple[str, ...]]

    @property
    def type_id(self) -> UUID:
        return self.levels[self.target].table.bound.type_id

    def result(self, release: schemas.ReleaseRef, limit: int) -> schemas.PathResult:
        tail = self.levels[-1]
        middle = self.target != len(self.levels) - 1
        return schemas.PathResult(
            release=release,
            type_id=self.type_id,
            items=_items(self.levels[self.target], self.paths, limit),
            total=len(self.paths),
            truncated=len(self.paths) > limit,
            tail_type_id=tail.table.bound.type_id if middle else None,
            tail=_items(tail, tail.prefixes, limit) if middle else [],
            tail_total=len(tail.prefixes) if middle else 0,
            steps=[
                schemas.QueryStep.model_validate(level.step, from_attributes=True)
                for level in self.levels
            ],
        )


def _items(level: Level, paths: dict[str, tuple[str, ...]], limit: int) -> list[schemas.PathRow]:
    return [
        schemas.PathRow(**level.objects[key].model_dump(), via=list(path))
        for key, path in islice(paths.items(), limit)
    ]


async def walk(execution: Execution, body: schemas.PathQuery) -> Walk:
    target = len(body.hops) if body.target is None else body.target
    if not 0 <= target <= len(body.hops):
        raise AppError(422, "validation.failed", "The answer position is outside the path.")
    table = await execution.catalog.table(planner.bound_type(execution.model, body.type_id))
    table.require_available()
    maximum = config.current().metric_rows_max
    start = execution.budget.statements
    objects: dict[str, schemas.ObjectRow] = {}
    async for page in object_pages(execution, table, body.filters):
        objects.update((row.key, row) for row in page)
        check_size(len(objects), maximum)
    first = step(table, body.filters, execution.budget.statements - start, len(objects))
    levels = [Level(table, objects, first, {key: (key,) for key in objects})]
    for hop in body.hops:
        levels.append(await _advance(execution, levels[-1], hop, maximum))

    # Keep one suffix per viable node; enumerating every complete chain can be exponential.
    suffixes: dict[str, tuple[str, ...]] = dict.fromkeys(levels[-1].prefixes, ())
    for level in reversed(levels[target:-1]):
        viable: dict[str, tuple[str, ...]] = {}
        for key, children in level.children.items():
            for child in children:
                if child in suffixes:
                    viable[key] = (child, *suffixes[child])
                    break
        suffixes = viable
    paths = {
        key: prefix + suffixes[key]
        for key, prefix in levels[target].prefixes.items()
        if key in suffixes
    }
    return Walk(levels, target, paths)
