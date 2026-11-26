"""A disconnected HTTP request releases its in-flight connector call."""

import asyncio
from dataclasses import replace
from typing import Never
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.statements import SelectQuery
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.query import api, schemas, service
from test_query_rows import published_table


@pytest.mark.parametrize("route", ["search", "detail", "related"])
async def test_disconnect_cancels_and_joins_the_pending_read(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def pending(db: AsyncSession, query: SelectQuery) -> Never:
        started.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("The read should only finish through cancellation.")

    class Disconnect(Request):
        async def is_disconnected(self) -> bool:
            return started.is_set()

    db = Mock(spec=AsyncSession)
    principal = Mock(spec=Principal)
    request = Disconnect({"type": "http"})
    model = published_table(monkeypatch)
    type_id = model.types[0].type_id
    relation = bindings.BoundRelation(
        uuid4(),
        uuid4(),
        "next",
        "Next",
        type_id,
        type_id,
        bindings.ForeignKeyHop("source", ("id",), ("id",)),
        None,
        None,
    )
    model = replace(model, relations=(relation,))
    monkeypatch.setattr(bindings, "bound_model", AsyncMock(return_value=model))
    monkeypatch.setattr(connectors, "select", pending)
    key = "WyIxIl0"  # ["1"]

    async def call_route() -> None:
        if route == "search":
            await api.search_objects(
                model.ontology_id, schemas.ObjectSearch(type_id=type_id), request, principal, db
            )
        elif route == "detail":
            await api.get_object(model.ontology_id, type_id, key, request, principal, db)
        else:
            await api.list_related_objects(
                model.ontology_id, type_id, key, request, principal, db, relation.relation_id
            )

    async with asyncio.timeout(3):
        with pytest.raises(HTTPException) as error:
            await call_route()

    assert error.value.status_code == 499
    assert cancelled.is_set()


async def test_connected_request_receives_the_result() -> None:
    result = object()

    class Connected(Request):
        async def is_disconnected(self) -> bool:
            return False

    async def work() -> object:
        await asyncio.sleep(0)
        return result

    assert await service.until_disconnected(Connected({"type": "http"}), work()) is result
