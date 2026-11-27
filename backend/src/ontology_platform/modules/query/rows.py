"""Map a connector page to objects, preserving cell positions and identity."""

from uuid import UUID

from ontology_platform.modules.connectors.statements import Rows, SelectQuery, SortKey, Value
from ontology_platform.modules.query import cursor, errors, schemas, values
from ontology_platform.modules.query.planner import Table


def after(
    position: list[str | None] | None, table: Table, order: tuple[SortKey, ...]
) -> tuple[Value, ...] | None:
    if position is None:
        return None
    if len(position) != len(order):
        raise errors.invalid_cursor()
    parsed: list[Value] = []
    for value, sort in zip(position, order, strict=True):
        column = table.columns[sort.column.name]
        if value is None:
            if column.name in table.bound.key_columns or not column.nullable:
                raise errors.invalid_cursor()
            parsed.append(None)
        else:
            try:
                parsed.append(values.parse_value(value, column))
            except ValueError:
                raise errors.invalid_cursor() from None
    return tuple(parsed)


def _object(
    table: Table, row: tuple[Value, ...], index: dict[str, int], cut: set[int]
) -> schemas.ObjectRow:
    keys = []
    for name in table.bound.key_columns:
        value = row[index[name]]
        if value is None or index[name] in cut:
            raise errors.source_mismatch()
        keys.append(schemas.SourceKey(column=name, value=values.string_value(value)))

    properties: dict[UUID, schemas.Scalar | None] = {}
    truncated = []
    for prop in table.bound.properties:
        slot = index[prop.column]
        raw = row[slot]
        properties[prop.property_id] = (
            values.string_value(raw)
            if raw is not None and prop.datatype == "decimal"
            else values.result_value(raw)
        )
        if slot in cut:
            truncated.append(prop.property_id)
    return schemas.ObjectRow(
        type_id=table.bound.type_id,
        key=cursor.encode_key([part.value for part in keys]),
        source=schemas.ObjectSource(
            data_source_id=table.bound.data_source_id,
            data_source_name=table.source_name,
            schema=table.bound.schema,
            table=table.bound.table,
            key=keys,
        ),
        values=properties,
        truncated=truncated,
    )


def objects(table: Table, query: SelectQuery, result: Rows) -> list[schemas.ObjectRow]:
    index = {column.name: i for i, column in enumerate(query.columns)}
    cuts: dict[int, set[int]] = {}
    for i, j in result.truncated:
        cuts.setdefault(i, set()).add(j)
    return [_object(table, row, index, cuts.get(i, set())) for i, row in enumerate(result.rows)]


def next_cursor(
    release: UUID, context: dict[str, object], query: SelectQuery, result: Rows
) -> str | None:
    if not result.has_more:
        return None
    last = result.rows[-1]
    slots = {column: i for i, column in enumerate(query.columns)}
    position = []
    for sort in query.order_by:
        i = slots[sort.column]
        # Continuing from a clipped sort value can repeat the previous page indefinitely.
        # A clipped key never gets here (it fails while mapping the row), so this is the sort.
        if (len(result.rows) - 1, i) in result.truncated:
            raise errors.sort_value_too_long()
        position.append(None if last[i] is None else values.string_value(last[i]))
    return cursor.encode_page(release, context, position)


def joined_objects(
    table: Table, query: SelectQuery, page: Rows
) -> list[tuple[str, schemas.ObjectRow]]:
    # ColumnRef includes the side, even when the two tables use identical key names.
    slots = {col: i for i, col in enumerate(query.columns)}
    main = {col.name: i for col, i in slots.items() if col.side == "main"}
    origin = [i for col, i in slots.items() if col.side == "joined"]
    cuts: dict[int, set[int]] = {}
    for r, c in page.truncated:
        cuts.setdefault(r, set()).add(c)
    pairs = []
    for r, record in enumerate(page.rows):
        cut = cuts.get(r, set())
        if any(record[i] is None or i in cut for i in origin):
            raise errors.source_mismatch()
        key = cursor.encode_key([values.string_value(record[i]) for i in origin])
        pairs.append((key, _object(table, record, main, cut)))
    return pairs
