"""Shared setup for the query HTTP tests."""

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import Element, Ontology
from support import PROBLEM_JSON, csrf_headers
from test_connectors_support import add_source, cache_table
from test_ontology_bindings_support import (
    foreign_key,
    property_binding,
    relation_binding,
    save,
    table,
    type_binding,
)
from test_ontology_support import add_elements, add_ontology, element, publish, sign_in


@dataclass
class QueryCatalog:
    ontology: Ontology
    source: DataSource
    coil: Element
    status: Element
    inspection: Element
    inspected_coil: Element
    inspections: Element

    @property
    def url(self) -> str:
        return f"/api/ontologies/{self.ontology.id}/objects"

    def coil_bindings(self, schema: str = "mes", name: str = "coil") -> list[dict[str, Any]]:
        target = table(self.source, name, ["coil_no"])
        target["schema"] = schema
        return [
            type_binding(self.coil, target, "coil"),
            property_binding(self.status, "coil", "status"),
        ]

    def inspection_binding(self, source: DataSource) -> dict[str, Any]:
        return type_binding(
            self.inspection, table(source, "quality_inspection", ["inspection_id"]), "inspection"
        )

    def bindings(self, schema: str = "mes", name: str = "coil") -> list[dict[str, Any]]:
        return [
            *self.coil_bindings(schema, name),
            self.inspection_binding(self.source),
            relation_binding(
                self.inspected_coil, "inspection", "coil", foreign_key(["coil_no"], ["coil_no"])
            ),
        ]


async def make_catalog(
    client: AsyncClient, db: AsyncSession, external: ExternalSource, *, writer: bool = False
) -> QueryCatalog:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    coil = element(ontology, "entity_type", "Coil", "钢卷")
    inspection = element(ontology, "entity_type", "Inspection", "质检")
    status = element(
        ontology, "property", "coilStatus", "状态", domain_id=coil.id, datatype="string"
    )
    inspected_coil = element(
        ontology,
        "relation_type",
        "inspectedCoil",
        "受检钢卷",
        domain_id=inspection.id,
        range_id=coil.id,
    )
    inspections = element(
        ontology,
        "relation_type",
        "inspections",
        "质检记录",
        domain_id=coil.id,
        range_id=inspection.id,
        inverse_id=inspected_coil.id,
    )
    await add_elements(db, coil, inspection, status, inspected_coil, inspections)
    inspected_coil.inverse_id = inspections.id
    await db.commit()
    source = await add_source(db, external, writer=writer)
    for name in ("coil", "quality_inspection"):
        await cache_table(db, source.id, external, "mes", name)
    return QueryCatalog(ontology, source, coil, status, inspection, inspected_coil, inspections)


async def publish_bindings(
    client: AsyncClient, catalog: QueryCatalog, items: list[dict[str, Any]] | None = None
) -> str:
    edits = await save(client, catalog.ontology, catalog.bindings() if items is None else items)
    assert edits.status_code == 200, edits.json()
    assert edits.json()["merged"] is True
    released = await publish(client, catalog.ontology)
    assert released.status_code == 201, released.json()
    release_id: str = released.json()["id"]
    return release_id


async def search(
    client: AsyncClient, catalog: QueryCatalog, type_: Element, **options: Any
) -> Response:
    return await client.post(
        f"{catalog.url}/search",
        json={"typeId": str(type_.id), **options},
        headers=csrf_headers(client),
    )


def assert_problem(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].split(";")[0] == PROBLEM_JSON
    problem = response.json()
    assert (problem["status"], problem["code"]) == (status, code)
