"""Startup warming of the process-local cache used by the axiom list."""

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.main import create_app
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import Element, Ontology
from ontology_platform.modules.ontology.rdf import axiom_categories
from ontology_platform.modules.ontology.rdf.axiom_categories import Prefixes, fragment_info
from ontology_platform.settings import Settings
from test_axiom_categories import ASSERTION_CATEGORIES, ASSERTION_SOURCE
from test_ontology_import import import_and_merge
from test_ontology_support import add_elements, add_ontology, sign_in

FIRST = "<urn:heat> rdfs:comment 'first' ."
SECOND = "<urn:heat> rdfs:comment 'second' ."


async def add_axioms(db: AsyncSession, key: str, *fragments: str) -> Ontology:
    ontology = await add_ontology(db, key)
    await add_elements(
        db,
        *(
            Element(ontology_id=ontology.id, kind="axiom", origin="manual", turtle=turtle)
            for turtle in fragments
        ),
    )
    return ontology


async def test_warmup_uses_the_list_cache(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    imported = await import_and_merge(client, ASSERTION_SOURCE)
    ontology_id = UUID(imported["ontology"]["id"])
    await add_elements(
        db,
        Element(
            ontology_id=ontology_id,
            kind="axiom",
            status="deprecated",
            origin="manual",
            turtle=FIRST,
        ),
    )
    fragment_info.cache_clear()

    warmed = await service.warm_axiom_categories(app.state.session_factory)
    assert warmed == len(ASSERTION_CATEGORIES)
    before = fragment_info.cache_info()
    response = await client.get(f"/api/ontologies/{ontology_id}/elements", params={"kind": "axiom"})
    assert response.status_code == 200, response.text
    assert {row["turtle"]: row["axiomCategory"] for row in response.json()} == ASSERTION_CATEGORIES
    after = fragment_info.cache_info()
    assert after.misses == before.misses
    assert after.hits >= before.hits + len(ASSERTION_CATEGORIES)


async def test_warmup_limits_the_most_recent_ontology(
    app: FastAPI, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    recent = await add_axioms(db, "recent", FIRST, SECOND)
    older = await add_axioms(db, "older", FIRST)
    recent.updated_at = older.updated_at + timedelta(days=1)
    await db.commit()
    monkeypatch.setattr(axiom_categories, "FRAGMENT_CACHE_SIZE", 1)
    fragment_info.cache_clear()

    assert await service.warm_axiom_categories(app.state.session_factory) == 1
    before = fragment_info.cache_info()
    assert before.currsize == 1
    recent_prefixes = tuple(sorted(service.header_of(recent).prefix_map().items()))
    for turtle in (FIRST, SECOND):
        fragment_info(turtle, recent_prefixes)
    assert fragment_info.cache_info().hits == before.hits + 1
    older_prefixes = tuple(sorted(service.header_of(older).prefix_map().items()))
    fragment_info(FIRST, older_prefixes)
    assert fragment_info.cache_info().misses == before.misses + 2


async def test_one_failed_ontology_does_not_stop_warmup(
    app: FastAPI,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    healthy = await add_axioms(db, "healthy", FIRST)
    broken = await add_axioms(db, "broken", SECOND)
    original = service._axiom_fields
    error = ValueError("cannot classify fragment")

    def classify(
        kind: str,
        turtle: str | None,
        prefixes: Prefixes,
        annotations: frozenset[str],
        properties: frozenset[str],
    ) -> dict[str, str | None]:
        if turtle == SECOND:
            raise error
        return original(kind, turtle, prefixes, annotations, properties)

    monkeypatch.setattr(service, "_axiom_fields", classify)
    fragment_info.cache_clear()
    with caplog.at_level(logging.ERROR, logger=service.__name__):
        assert await service.warm_axiom_categories(app.state.session_factory) == 1

    errors = [r for r in caplog.records if r.exc_info and r.exc_info[1] is error]
    assert len(errors) == 1
    assert str(broken.id) in errors[0].getMessage()
    before = fragment_info.cache_info()
    fragment_info(FIRST, tuple(sorted(service.header_of(healthy).prefix_map().items())))
    assert fragment_info.cache_info().hits == before.hits + 1


async def test_restart_cancels_and_joins_running_warmup(
    settings: Settings, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sign_in(client, db, Role.ADMIN)
    imported = await import_and_merge(client, ASSERTION_SOURCE)
    ontology_id = UUID(imported["ontology"]["id"])
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def pause(
        db: AsyncSession, ontology: Ontology
    ) -> tuple[Prefixes, frozenset[str], frozenset[str]]:
        assert ontology.id == ontology_id
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0)
            cancelled.set()
            raise
        raise AssertionError("unexpected end of warmup")

    monkeypatch.setattr(service, "_axiom_vocabulary", pause)
    restarted = create_app(settings)
    existing = asyncio.all_tasks()
    async with asyncio.timeout(5), restarted.router.lifespan_context(restarted):
        await started.wait()
        assert not cancelled.is_set()
    assert cancelled.is_set()
    assert asyncio.all_tasks() <= existing
