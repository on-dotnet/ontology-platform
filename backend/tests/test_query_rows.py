"""The public search and detail services consume positional connector rows."""

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.schemas import (
    CatalogColumn,
    CatalogTableCopy,
    DataSourceRef,
)
from ontology_platform.modules.connectors.statements import Rows, SelectQuery
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.query import planner, schemas, service


def published_table(monkeypatch: pytest.MonkeyPatch) -> bindings.BoundModel:
    note = bindings.BoundProperty(uuid4(), uuid4(), "note", "Note", "string", None, "note")
    size = bindings.BoundProperty(uuid4(), uuid4(), "size", "Size", "decimal", None, "id")
    target = bindings.BoundType(
        uuid4(), uuid4(), "Slab", "Slab", None, uuid4(), "mes", "slab", ("id",), (note, size)
    )
    model = bindings.BoundModel(uuid4(), uuid4(), 3, (target,), ())
    table = CatalogTableCopy(
        data_source_id=target.data_source_id,
        schema="mes",
        name="slab",
        kind="table",
        comment=None,
        columns=(
            CatalogColumn(
                name="id", type="bigint", family="integer", nullable=False, comment=None, position=1
            ),
            CatalogColumn(
                name="note", type="text", family="string", nullable=True, comment=None, position=2
            ),
        ),
        primary_key=("id",),
        foreign_keys=(),
        refreshed_at=datetime.now(UTC),
    )
    source = DataSourceRef(
        id=target.data_source_id,
        name="MES",
        kind="postgresql",
        status="active",
        allow_samples=False,
        has_credential=True,
        catalog_status="ready",
    )
    monkeypatch.setattr(bindings, "bound_model", AsyncMock(return_value=model))
    monkeypatch.setattr(connectors, "get_catalog_table", AsyncMock(return_value=table))
    monkeypatch.setattr(connectors, "get_data_source_ref", AsyncMock(return_value=source))
    return model


async def test_cut_cells_are_reported_on_the_right_row_and_property(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = published_table(monkeypatch)
    target = model.types[0]
    note, size = target.properties

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        columns = [column.name for column in query.columns]
        assert sorted(columns) == ["id", "note"]
        data: list[dict[str, int | str | None]] = [
            {"id": 21, "note": None},
            {"id": 22, "note": "x" * 2000},
        ]
        return Rows(
            tuple(tuple(row[name] for name in columns) for row in data),
            has_more=False,
            truncated=frozenset({(1, columns.index("note"))}),
        )

    monkeypatch.setattr(connectors, "select", read)
    page = await service.search(
        Mock(spec=AsyncSession), model.ontology_id, schemas.ObjectSearch(type_id=target.type_id)
    )
    first, second = page.items
    assert first.truncated == []
    assert second.truncated == [note.property_id]
    assert first.values == {note.property_id: None, size.property_id: "21"}
    assert second.values == {note.property_id: "x" * 2000, size.property_id: "22"}
    assert page.next_cursor is None


@pytest.mark.parametrize("key_parts", [[], ["1", "2"], [None], ["1.5"], [True], {"id": "1"}])
async def test_invalid_key_never_reaches_the_connector(
    monkeypatch: pytest.MonkeyPatch, key_parts: object
) -> None:
    model = published_table(monkeypatch)
    read = AsyncMock()
    monkeypatch.setattr(connectors, "select", read)
    key = base64.urlsafe_b64encode(json.dumps(key_parts).encode()).decode().rstrip("=")
    with pytest.raises(AppError) as error:
        await service.get_object(
            Mock(spec=AsyncSession), model.ontology_id, model.types[0].type_id, key
        )
    assert (error.value.status, error.value.code) == (404, "query.object_not_found")
    read.assert_not_awaited()


async def test_paging_preserves_a_long_sort_value(monkeypatch: pytest.MonkeyPatch) -> None:
    model = published_table(monkeypatch)
    target = model.types[0]
    note = target.properties[0]
    text = "a" * 1600

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        more = query.after is None
        if not more:
            assert query.after == (text, 17)
        record: dict[str, int | str] = {"id": 17 if more else 23, "note": text if more else "b"}
        return Rows((tuple(record[col.name] for col in query.columns),), has_more=more)

    monkeypatch.setattr(connectors, "select", read)
    db = Mock(spec=AsyncSession)
    body = schemas.ObjectSearch(
        type_id=target.type_id, limit=1, sort=[schemas.Sort(property_id=note.property_id)]
    )
    first = await service.search(db, model.ontology_id, body)
    assert first.items[0].values[note.property_id] == text
    assert first.next_cursor
    assert len(first.next_cursor) <= schemas.CURSOR_MAX_LENGTH
    body.cursor = first.next_cursor
    second = await service.search(db, model.ontology_id, body)
    assert second.items[0].values[note.property_id] == "b"
    assert second.next_cursor is None


@pytest.mark.parametrize(
    ("text", "clipped"),
    [
        # The connector cut the value, so the next page cannot be located from it.
        ("a" * 2000, True),
        # The whole value arrived, but it does not compress into a cursor.
        ("".join(chr(0x4E00 + index) for index in range(2000)), False),
    ],
    ids=["clipped", "incompressible"],
)
async def test_a_sort_value_too_long_to_continue_from_is_reported_as_such(
    monkeypatch: pytest.MonkeyPatch, text: str, clipped: bool
) -> None:
    model = published_table(monkeypatch)
    target = model.types[0]

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        projected = [c.name for c in query.columns]
        record: dict[str, int | str] = {"id": 17, "note": text}
        return Rows(
            (tuple(record[name] for name in projected),),
            has_more=True,
            truncated=frozenset({(0, projected.index("note"))} if clipped else ()),
        )

    monkeypatch.setattr(connectors, "select", read)
    body = schemas.ObjectSearch(
        type_id=target.type_id,
        limit=1,
        sort=[schemas.Sort(property_id=target.properties[0].property_id)],
    )
    with pytest.raises(AppError) as error:
        await service.search(Mock(spec=AsyncSession), model.ontology_id, body)
    assert (error.value.status, error.value.code) == (422, "query.sort_value_too_long")


async def test_a_key_too_long_on_a_sorted_page_has_a_specific_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = published_table(monkeypatch)
    target = model.types[0]
    # Distinct characters, so that compression cannot bring the key within its limit.
    key = "".join(chr(0x4E00 + index) for index in range(2000))

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        record: dict[str, int | str] = {"id": key, "note": "b"}
        return Rows((tuple(record[col.name] for col in query.columns),), has_more=True)

    monkeypatch.setattr(connectors, "select", read)
    body = schemas.ObjectSearch(
        type_id=target.type_id,
        limit=1,
        sort=[schemas.Sort(property_id=target.properties[0].property_id)],
    )
    with pytest.raises(AppError) as error:
        await service.search(Mock(spec=AsyncSession), model.ontology_id, body)
    assert (error.value.status, error.value.code) == (422, "query.key_too_long")


@pytest.mark.parametrize("use_alias", [False, True], ids=["bound-id", "inverse-alias"])
async def test_a_hop_never_silently_picks_between_two_target_types(
    monkeypatch: pytest.MonkeyPatch, use_alias: bool
) -> None:
    model = published_table(monkeypatch)
    origin = model.types[0]
    other = replace(origin, type_id=uuid4(), binding_id=uuid4())
    inverse_id = uuid4()
    relation = bindings.BoundRelation(
        uuid4(),
        uuid4(),
        "next",
        "Next",
        origin.type_id,
        origin.type_id,
        bindings.ForeignKeyHop("source", ("id",), ("id",)),
        inverse_id,
        "Previous",
    )
    model = replace(
        model,
        types=(origin, other),
        relations=(relation, replace(relation, binding_id=uuid4(), target_type_id=other.type_id)),
    )
    monkeypatch.setattr(bindings, "bound_model", AsyncMock(return_value=model))
    read = AsyncMock()
    monkeypatch.setattr(connectors, "select", read)
    with pytest.raises(AppError) as error:
        await service.related(
            Mock(spec=AsyncSession),
            model.ontology_id,
            origin.type_id,
            "WyIxIl0",
            relation_id=inverse_id if use_alias else relation.relation_id,
            direction="in" if use_alias else "out",
            limit=1,
            cursor=None,
        )
    assert (error.value.status, error.value.code) == (409, "query.source_mismatch")
    read.assert_not_awaited()


def test_explicit_binding_wins_over_its_inverse_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    model = published_table(monkeypatch)
    origin = model.types[0].type_id
    next_id, previous_id = uuid4(), uuid4()
    next_step = bindings.BoundRelation(
        next_id,
        uuid4(),
        "next",
        "Next",
        origin,
        origin,
        bindings.ForeignKeyHop("source", ("next_id",), ("id",)),
        previous_id,
        "Previous",
    )
    previous_step = replace(
        next_step,
        relation_id=previous_id,
        binding_id=uuid4(),
        local_name="previous",
        label="Previous",
        join=bindings.ForeignKeyHop("source", ("previous_id",), ("id",)),
        inverse_id=next_id,
        inverse_label="Next",
    )
    model = replace(model, relations=(next_step, previous_step))
    directions: tuple[schemas.Direction, ...] = ("in", "out")
    for bound in model.relations:
        for direction in directions:
            step = planner.resolve_relation(model, origin, bound.relation_id, direction)
            assert (step.relation, step.direction) == (bound, direction)


def test_two_unusable_inverse_bindings_keep_the_outgoing_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = published_table(monkeypatch)
    origin = model.types[0]
    other = replace(origin, type_id=uuid4(), binding_id=uuid4())
    first_id, second_id = uuid4(), uuid4()
    first = bindings.BoundRelation(
        first_id,
        uuid4(),
        "first",
        "First",
        origin.type_id,
        other.type_id,
        bindings.ForeignKeyHop("source", ("missing_first",), ("id",)),
        second_id,
        "Second",
    )
    second = bindings.BoundRelation(
        second_id,
        uuid4(),
        "second",
        "Second",
        other.type_id,
        origin.type_id,
        bindings.ForeignKeyHop("source", ("missing_second",), ("id",)),
        first_id,
        "First",
    )
    model = replace(model, types=(origin, other), relations=(first, second))
    listed = planner.relations(model, origin.type_id, {first.binding_id, second.binding_id})
    assert {(item.relation_id, item.direction) for item in listed[origin.type_id]} == {
        (first_id, "out"),
        (second_id, "in"),
    }


def test_missing_relation_endpoints_do_not_hide_valid_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = published_table(monkeypatch)
    origin = model.types[0]
    target = replace(origin, type_id=uuid4(), binding_id=uuid4())
    relation = bindings.BoundRelation(
        uuid4(),
        uuid4(),
        "next",
        "Next",
        origin.type_id,
        target.type_id,
        bindings.ForeignKeyHop("source", ("id",), ("id",)),
        None,
        None,
    )
    model = replace(
        model,
        types=(origin, target),
        relations=(
            replace(relation, relation_id=uuid4(), source_type_id=uuid4()),
            replace(relation, relation_id=uuid4(), target_type_id=uuid4()),
            relation,
        ),
    )
    listed = planner.relations(model)
    assert set(listed) == {origin.type_id, target.type_id}
    [outward] = listed[origin.type_id]
    [inward] = listed[target.type_id]
    assert (outward.relation_id, outward.direction) == (relation.relation_id, "out")
    assert (inward.relation_id, inward.direction) == (relation.relation_id, "in")


@pytest.mark.parametrize("limit", [0, 201])
async def test_direct_hop_call_observes_the_page_limit(limit: int) -> None:
    with pytest.raises(AppError) as error:
        await service.related(
            Mock(spec=AsyncSession),
            uuid4(),
            uuid4(),
            "key",
            relation_id=uuid4(),
            direction="out",
            limit=limit,
            cursor=None,
        )
    assert (error.value.status, error.value.code) == (422, "validation.failed")
