"""M3 end to end (spec 003, section 15, "端到端"): data source → catalog → AI binding suggestion
(fake gateway) → review → release → query a heat and hop to its coils → the same over MCP with
an access token.

`run_flow` is also the "全流程" of the credential scan in test_m3_secret_scan.py: its requests go
through the public interfaces, and the production worker runs the queued jobs. It keeps
every response and the gateway that saw what the model saw.
"""

import asyncio
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform import worker
from ontology_platform.modules.ai import qa
from ontology_platform.modules.ai.binding_prompts import ColumnsOut
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.connectors import config as connectors_config
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs import runner
from ontology_platform.modules.jobs import service as queue
from ontology_platform.modules.jobs.models import Job
from ontology_platform.settings import Settings
from support import csrf_headers, make_client
from test_ai_binding_suggest import EXPECTED, CatalogGateway, _relation_out, column, table_match
from test_connectors_support import admin_rows
from test_mcp_support import call_tool, new_token
from test_ontology_import import STEEL, import_and_merge
from test_ontology_support import accept_and_merge

NS = "urn:synthetic:metals:"
HEAT = "H2401001"
# Heat → casting sequence → slab → rolling event → coil, every hop from the source side.
HOPS = [
    ("castIn", "CastingSequence", None),
    ("producesSlab", "Slab", "S240100101"),
    ("rolledIn", "RollingEvent", None),
    ("producesCoil", "Coil", None),
]


@dataclass
class Flow:
    ontology_id: str
    source_id: str
    release_id: str
    token: str
    token_id: str
    ids: dict[str, str]
    # Everything sent to the model.
    gateway: CatalogGateway
    # Every response of the flow, the platform's own client and the agent's.
    responses: list[Response] = field(default_factory=list)
    api_pages: list[dict[str, Any]] = field(default_factory=list)
    mcp_pages: list[dict[str, Any]] = field(default_factory=list)


def _keep(responses: list[Response]) -> Any:
    async def hook(response: Response) -> None:
        await response.aread()
        responses.append(response)

    return hook


async def _run_jobs(settings: Settings, gateway: CatalogGateway) -> int:
    # Shut the worker down on its first empty claim, using its normal shutdown callback.
    stop: Callable[[], None]
    claim = queue.claim
    count = 0

    def on_signal(_: int, callback: Callable[[], None]) -> None:
        nonlocal stop
        stop = callback

    async def claim_until_empty(db: AsyncSession, worker_id: str) -> Job | None:
        nonlocal count
        job = await claim(db, worker_id)
        if job is None:
            stop()
        else:
            count += 1
        return job

    with pytest.MonkeyPatch.context() as patch:
        worker_settings = settings.model_copy(update={"worker_concurrency": 1})
        patch.setattr(worker, "Settings", lambda: worker_settings)
        patch.setattr(worker, "OpenAIGateway", Mock(return_value=gateway))
        patch.setattr(runner, "_handlers", {})
        patch.setattr(qa, "_listeners", [])
        for name in (
            "register_extractor",
            "register_vision_transcriber",
            "register_usage_provider",
        ):
            patch.setattr(worker, name, Mock())
        loop = asyncio.get_running_loop()
        patch.setattr(loop, "add_signal_handler", on_signal)
        patch.setattr(loop, "remove_signal_handler", Mock())
        patch.setattr(queue, "claim", claim_until_empty)
        async with asyncio.timeout(60):
            await worker.run()
    return count


def _gateway(ids: dict[str, str]) -> CatalogGateway:
    """The model answers what expected-bindings.toml says, each relation from its source type."""
    expected = tomllib.loads(EXPECTED.read_text("utf-8"))
    uuids = {iri: UUID(value) for iri, value in ids.items()}
    return CatalogGateway(
        [table_match(ids[t["type"]], t["table"], list(t["key"])) for t in expected["types"]],
        {
            uuids[t["type"]]: ColumnsOut(
                properties=[column(ids[p], c) for p, c in t["properties"].items()],
                relations=[
                    _relation_out(r, uuids)
                    for r in expected["relations"]
                    if r["source"] == t["type"]
                ],
            )
            for t in expected["types"]
        },
    )


def _ok(response: Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def _structured(result: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is False, result
    content: dict[str, Any] = result["structuredContent"]
    return content


def _pick(page: dict[str, Any], value: str | None) -> dict[str, Any]:
    """The row whose source key is `value`, or the only row."""
    rows = page["items"]
    if value is None:
        assert len(rows) == 1, rows
        row: dict[str, Any] = rows[0]
        return row
    [row] = [r for r in rows if [k["value"] for k in r["source"]["key"]] == [value]]
    return row


async def run_flow(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> Flow:
    monkeypatch.setattr(connectors_config, "_configured", settings)
    responses: list[Response] = []
    client.event_hooks["response"].append(_keep(responses))
    token, token_id = await new_token(client, db, Role.ADMIN, ["ontology:read", "objects:read"])
    imported = await import_and_merge(client, STEEL, filename="steel.ttl")
    ontology_id = imported["ontology"]["id"]
    elements = await client.get(f"/api/ontologies/{ontology_id}/elements")
    assert elements.status_code == 200, elements.text
    ids = {e["iri"]: e["id"] for e in elements.json() if e["iri"]}
    gateway = _gateway(ids)
    csrf = csrf_headers(client)

    # A data source on the steel sample, tested, its catalog read and browsed.
    source = _ok(
        await client.post(
            "/api/data-sources",
            json={
                "name": "MES",
                "kind": "postgresql",
                "host": external_source.host,
                "port": external_source.port,
                "database": external_source.database,
                "username": external_source.reader,
                "password": external_source.reader_password,
                "sslMode": "disable",
                "schemas": ["mes"],
                "allowSamples": True,
            },
            headers=csrf,
        ),
        201,
    )
    base = f"/api/data-sources/{source['id']}"
    assert _ok(await client.post(f"{base}/test", headers=csrf))["ok"] is True
    _ok(await client.post(f"{base}/catalog/refresh", headers=csrf), 202)
    assert await _run_jobs(settings, gateway) == 1
    assert _ok(await client.get(base))["catalog"]["status"] == "ready"
    _ok(await client.get(f"{base}/catalog/tables/mes/heat"))

    # The AI suggests the bindings; they wait for review, then are merged and released.
    requested = _ok(
        await client.post(
            f"/api/ontologies/{ontology_id}/binding-suggestions",
            json={"dataSourceId": source["id"], "schemas": ["mes"]},
            headers=csrf,
        ),
        202,
    )
    assert await _run_jobs(settings, gateway) == 1
    suggestion = _ok(await client.get(f"/api/binding-suggestions/{requested['id']}"))
    assert (suggestion["status"], suggestion["dropped"]) == ("succeeded", 0)
    assert suggestion["samplesSent"] is True
    change_set_id = suggestion["changeSetId"]
    detail = _ok(await client.get(f"/api/change-sets/{change_set_id}"))
    assert detail["status"] == "open"
    url = f"/api/ontologies/{ontology_id}/objects"
    unreleased = await client.post(f"{url}/search", json={"typeId": ids[NS + "Heat"]}, headers=csrf)
    # This only establishes that there is no effective release yet.
    assert unreleased.status_code == 409
    assert unreleased.headers["content-type"] == "application/problem+json"
    assert unreleased.json()["code"] == "query.no_release"
    assert (await accept_and_merge(client, UUID(change_set_id)))["skipped"] == []
    release = _ok(
        await client.post(
            f"/api/ontologies/{ontology_id}/releases", json={"title": "M3"}, headers=csrf
        ),
        201,
    )

    # A heat, then hop by hop to its coils.
    flow = Flow(
        ontology_id=ontology_id,
        source_id=source["id"],
        release_id=release["id"],
        token=token,
        token_id=token_id,
        ids=ids,
        gateway=gateway,
        responses=responses,
    )
    heats = _ok(
        await client.post(
            f"{url}/search", json={"typeId": ids[NS + "Heat"], "limit": 200}, headers=csrf
        )
    )
    flow.api_pages.append(heats)
    origin, origin_type = _pick(heats, HEAT), ids[NS + "Heat"]
    for relation, target, value in HOPS:
        page = _ok(
            await client.get(
                f"{url}/{origin_type}/{origin['key']}/related",
                params={"relationId": ids[NS + relation], "direction": "out", "limit": "200"},
            )
        )
        assert page["typeId"] == ids[NS + target]
        flow.api_pages.append(page)
        if target != "Coil":
            origin, origin_type = _pick(page, value), ids[NS + target]

    # The same over MCP, naming things the way an agent would.
    async with make_client(app) as agent:
        agent.event_hooks["response"].append(_keep(responses))
        listed = _structured(await call_tool(agent, token, "list_ontologies"))
        assert ontology_id in [o["id"] for o in listed["ontologies"]]
        heats = _structured(
            await call_tool(
                agent,
                token,
                "search_objects",
                {"ontology": ontology_id, "type": NS + "Heat", "limit": 200},
            )
        )
        flow.mcp_pages.append(heats)
        origin, type_ = _pick(heats, HEAT), NS + "Heat"
        for relation, target, value in HOPS:
            page = _structured(
                await call_tool(
                    agent,
                    token,
                    "get_related_objects",
                    {
                        "ontology": ontology_id,
                        "type": type_,
                        "key": origin["key"],
                        "relation": NS + relation,
                        "direction": "out",
                        "limit": 200,
                    },
                )
            )
            flow.mcp_pages.append(page)
            if target != "Coil":
                origin, type_ = _pick(page, value), NS + target
    return flow


async def test_from_a_data_source_to_coils_over_the_api_and_mcp(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = await run_flow(app, client, db, external_source, settings, monkeypatch)

    # Every page names the release in effect; MCP answers exactly what /api answers.
    assert len(flow.api_pages) == len(HOPS) + 1
    assert all(page["release"]["id"] == flow.release_id for page in flow.api_pages)
    assert flow.mcp_pages == flow.api_pages
    coils = flow.api_pages[-1]
    # The same path in SQL: the heat's slab S240100101, its rolling, that rolling's coils.
    expected = admin_rows(
        external_source,
        "SELECT c.coil_no FROM mes.slab s"
        " JOIN mes.slab_rolling sr USING (slab_no) JOIN mes.coil c USING (rolling_id)"
        " WHERE s.heat_no = %s AND s.slab_no = %s ORDER BY c.coil_no",
        HEAT,
        "S240100101",
    )
    assert expected
    assert sorted(k["value"] for row in coils["items"] for k in row["source"]["key"]) == [
        coil for (coil,) in expected
    ]
    assert all(row["typeId"] == flow.ids[NS + "Coil"] for row in coils["items"])
    assert coils["nextCursor"] is None
    # Every MCP call is audited under the token.
    called = await db.scalars(select(AuditEvent).where(AuditEvent.action == "mcp.tool_called"))
    events = called.all()
    assert all(
        (e.target_id, e.detail["tokenId"], e.detail["code"]) == (flow.token_id, flow.token_id, "ok")
        for e in events
    )
    assert Counter((e.detail["tool"], e.detail["ontology"]) for e in events) == {
        ("list_ontologies", None): 1,
        ("search_objects", flow.ontology_id): 1,
        ("get_related_objects", flow.ontology_id): len(HOPS),
    }
