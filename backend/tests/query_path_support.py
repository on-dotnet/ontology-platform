"""Published QA demo bindings on the steel connector fixture."""

import tomllib
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import Ontology
from ontology_platform.modules.query import schemas
from test_connectors_support import add_source, cache_table
from test_ontology_bindings_support import (
    property_binding,
    relation_binding,
    save,
    table,
    type_binding,
)
from test_ontology_import import import_and_merge
from test_ontology_support import publish, sign_in
from test_qa_demo_import import EX, FIXTURES
from test_query_paging import SteelObjects


@pytest.fixture(name="qa_steel")
async def qa_steel_fixture(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> SteelObjects:
    await sign_in(client, db, Role.ADMIN)
    imported = await import_and_merge(client, (FIXTURES / "ontology.ttl").read_bytes())
    ontology = await db.get(Ontology, UUID(imported["ontology"]["id"]))
    assert ontology is not None
    response = await client.get(f"/api/ontologies/{ontology.id}/elements")
    assert response.status_code == 200
    ids = {e["iri"]: e["id"] for e in response.json()}
    source = await add_source(db, external_source)
    expected = tomllib.loads((FIXTURES / "expected-bindings.toml").read_text("utf-8"))
    refs = {t["type"]: t["table"] for t in expected["types"]}
    edits: list[dict[str, Any]] = []
    for t in expected["types"]:
        name = t["table"]
        await cache_table(db, source.id, external_source, t["schema"], name)
        edits.append(type_binding(ids[t["type"]], table(source, name, t["key"]), name))
        edits.extend(property_binding(ids[p], name, col) for p, col in t["properties"].items())
    for r in expected["relations"]:
        join = r["join"]
        if join["kind"] == "link_table":
            await cache_table(db, source.id, external_source, join["schema"], join["table"])
        edits.append(
            relation_binding(
                ids[r["relation"]],
                refs[r["source"]],
                refs[r["target"]],
                {"target": "join", "join": join},
            )
        )
    saved = await save(client, ontology, edits)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    release = await publish(client, ontology)
    assert release.status_code == 201, release.text
    return SteelObjects(
        ontology,
        {iri.removeprefix(EX): key for iri, key in ids.items() if iri},
        {key: release.json()[key] for key in ("id", "version")},
        str(source.id),
        source.name,
    )


def demo_path(
    steel: SteelObjects, *, failed: bool = False, reverse: bool = False
) -> schemas.PathQuery:
    ids = steel.ids
    grade = schemas.Filter(property_id=UUID(ids["steelGrade"]), op="eq", value="Q235B")
    inspection = (
        [schemas.Filter(property_id=UUID(ids["passed"]), op="eq", value=False)] if failed else []
    )
    hops = [
        schemas.PathHop(
            relation_id=UUID(ids[name]), direction="in" if name == "inspects" else "out"
        )
        for name in ("castIn", "producesSlab", "rolledIn", "producesCoil", "inspects")
    ]
    if reverse:
        hops.reverse()
        for hop in hops:
            hop.direction = "in" if hop.direction == "out" else "out"
        hops[-1].filters = [grade]
        return schemas.PathQuery(
            type_id=UUID(ids["QualityInspection"]), filters=inspection, hops=hops
        )
    hops[-1].filters = inspection
    return schemas.PathQuery(type_id=UUID(ids["Heat"]), filters=[grade], hops=hops)
