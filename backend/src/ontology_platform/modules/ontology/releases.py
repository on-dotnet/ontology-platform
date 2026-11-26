"""Releases: publish checks, immutable snapshots, export and activation (spec 001 section 6).

Moved out of service.py unchanged.
"""

import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.ontology import binding_rules, rules, schemas
from ontology_platform.modules.ontology.models import (
    BINDING_KINDS,
    DATATYPES,
    SEMANTIC_KINDS,
    Element,
    Ontology,
    Release,
)
from ontology_platform.modules.ontology.service import (
    ReleaseInvalidError,
    _elements,
    _kind_order,
    _now,
    _ontology_or_404,
    element_out,
    header_of,
)
from ontology_platform.modules.ontology.turtle import export_turtle


def release_problems(elements: Sequence[Element]) -> list[schemas.ReleaseProblem]:
    """Publish checks (spec section 6) over the working version."""
    by_id = {element.id: element for element in elements}
    active_elements = sorted((e for e in elements if e.status == "active"), key=_kind_order)
    problems: list[schemas.ReleaseProblem] = []

    def report(code: str, element: Element, message: str) -> None:
        problems.append(schemas.ReleaseProblem(code=code, element_id=element.id, message=message))

    if not active_elements:
        message = "The working version has no elements yet"
        return [schemas.ReleaseProblem(code="release.empty", element_id=None, message=message)]

    def active(element_id: UUID | None, *kinds: str) -> bool:
        target = by_id.get(element_id) if element_id is not None else None
        return target is not None and target.kind in kinds and target.status == "active"

    def reference(element: Element, element_id: UUID | None, code: str, what: str) -> None:
        # Imported elements may lack a reference (OWL allows it); a given one must be usable.
        if element_id is None and element.iri is not None:
            return
        if not active(element_id, "entity_type"):
            report(code, element, f"The {what} is missing or inactive")

    nodes = {str(e.id): binding_rules.element_node(e) for e in elements}
    for element in active_elements:
        if element.kind == "axiom":
            continue  # checked when merged; kept as written
        if element.kind in BINDING_KINDS:
            # Bindings have no names; the rules they were merged under must still hold.
            for problem in binding_rules.node_problems(nodes[str(element.id)], nodes):
                report("release.invalid_binding", element, problem.message)
            continue
        imported = element.iri is not None
        naming = rules.local_name_problem(element.kind, element.local_name or "", imported=imported)
        if naming:
            report("release.invalid_local_name", element, naming)
        if rules.is_blank(element.label_zh) and not imported:
            report("release.missing_label", element, "labelZh is empty")
        if element.kind == "entity_type":
            if element.parent_id is not None and not active(element.parent_id, "entity_type"):
                report("release.invalid_parent", element, "The parent type is missing or inactive")
            continue
        if element.kind == "constraint":
            if not active(element.domain_id, "entity_type"):
                report("release.invalid_domain", element, "The target type is missing or inactive")
            for rule in element.rules or []:
                path = UUID(str(rule["pathId"]))
                class_id = UUID(str(rule["classId"])) if rule.get("classId") else None
                if not active(path, *rules.RULE_PATH_KINDS) or (
                    class_id is not None and not active(class_id, "entity_type")
                ):
                    message = "A rule refers to an element that is missing or inactive"
                    report("release.invalid_constraint", element, message)
                    break
            continue
        reference(element, element.domain_id, "release.invalid_domain", "domain")
        if element.kind == "relation_type":
            reference(element, element.range_id, "release.invalid_range", "range")
            if element.inverse_id is not None and not active(element.inverse_id, "relation_type"):
                message = "The inverse relation is missing or inactive"
                report("release.invalid_inverse", element, message)
        # An imported property may have no datatype (its range is kept as an axiom).
        missing_ok = element.datatype is None and imported
        if element.kind == "property" and element.datatype not in DATATYPES and not missing_ok:
            report("release.invalid_datatype", element, "The datatype is missing or unknown")

    for element in active_elements:
        if element.kind != "entity_type":
            continue
        current = element.parent_id
        seen: set[UUID] = set()
        while current is not None and current not in seen and current != element.id:
            seen.add(current)
            parent = by_id.get(current)
            current = parent.parent_id if parent else None
        if current == element.id:
            report("release.cyclic_hierarchy", element, "The type hierarchy loops back here")
    return problems


def _release_out(release: Release, active_release_id: UUID | None) -> schemas.ReleaseSummary:
    return schemas.ReleaseSummary(
        id=release.id,
        ontology_id=release.ontology_id,
        version=release.version,
        title=release.title,
        notes=release.notes,
        element_count=release.element_count,
        binding_count=release.binding_count,
        is_active=release.id == active_release_id,
        created_by=release.created_by,
        created_at=release.created_at,
    )


def _without_content() -> tuple[Any, ...]:
    return (defer(Release.snapshot), defer(Release.turtle))


async def _release_or_404(db: AsyncSession, release_id: UUID, *, content: bool = False) -> Release:
    statement = select(Release).where(Release.id == release_id)
    if not content:
        statement = statement.options(*_without_content())
    release = await db.scalar(statement)
    if release is None:
        raise AppError(404, "release.not_found", "Release not found.")
    return release


async def list_releases(db: AsyncSession, ontology_id: UUID) -> list[schemas.ReleaseSummary]:
    """Newest version first."""
    ontology = await _ontology_or_404(db, ontology_id)
    releases = await db.scalars(
        select(Release)
        .options(*_without_content())
        .where(Release.ontology_id == ontology_id)
        .order_by(Release.version.desc()),
    )
    return [_release_out(release, ontology.active_release_id) for release in releases]


async def publish_release(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.ReleaseCreate,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.ReleaseSummary:
    """Check the working version, then store an immutable snapshot as the next version and make
    it the current one. Raises `ReleaseInvalidError` when the checks fail."""
    ontology = await _ontology_or_404(db, ontology_id, lock=True)
    elements = await _elements(db, ontology_id, all_kinds=True)
    problems = release_problems(elements)
    if problems:
        raise ReleaseInvalidError(problems)
    # Bindings are part of the snapshot (spec 003, 6.4) but neither of the Turtle nor of the
    # element count; the export must not rely on bindings having no IRI.
    snapshot = [
        element_out(element, ontology.base_iri)
        for element in elements
        if element.status == "active"
    ]
    semantic = [element for element in snapshot if element.kind in SEMANTIC_KINDS]
    latest = await db.scalar(
        select(func.max(Release.version)).where(Release.ontology_id == ontology_id),
    )
    version = (latest or 0) + 1
    now = _now()
    header = header_of(ontology)
    turtle = await asyncio.to_thread(export_turtle, header, semantic, version=version, created=now)
    release = Release(
        id=uuid4(),
        ontology_id=ontology_id,
        version=version,
        title=body.title,
        notes=rules.clean_text(body.notes),
        snapshot=[element.model_dump(mode="json", by_alias=True) for element in snapshot],
        header={"ontologyIri": header.ontology_iri, "prefixes": header.prefix_map()},
        turtle=turtle,
        turtle_sha256=hashlib.sha256(turtle.encode()).hexdigest(),
        element_count=len(semantic),
        binding_count=len(snapshot) - len(semantic),
        created_by=actor,
        created_at=now,
    )
    db.add(release)
    await db.flush()
    ontology.active_release_id = release.id
    ontology.updated_at = now
    audit.record(
        db,
        "release.published",
        actor_id=actor,
        target_type="release",
        target_id=str(release.id),
        detail={
            "ontologyId": str(ontology_id),
            "version": version,
            "elementCount": len(semantic),
            "bindingCount": len(snapshot) - len(semantic),
        },
        ip=ip,
    )
    await db.commit()
    return _release_out(release, release.id)


async def get_release(db: AsyncSession, release_id: UUID) -> schemas.ReleaseSummary:
    release = await _release_or_404(db, release_id)
    active_id = await db.scalar(
        select(Ontology.active_release_id).where(Ontology.id == release.ontology_id),
    )
    return _release_out(release, active_id)


async def export_release(db: AsyncSession, release_id: UUID) -> tuple[str, str]:
    """The Turtle stored at publish time, and a file name for it."""
    release = await _release_or_404(db, release_id, content=True)
    key = await db.scalar(select(Ontology.key).where(Ontology.id == release.ontology_id))
    return release.turtle, f"{key}-v{release.version}.ttl"


async def activate_release(
    db: AsyncSession,
    release_id: UUID,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.ReleaseSummary:
    """Make the release the ontology's current version (also how a rollback is done)."""
    release = await _release_or_404(db, release_id)
    ontology = await _ontology_or_404(db, release.ontology_id, lock=True)
    previous = ontology.active_release_id
    ontology.active_release_id = release.id
    ontology.updated_at = _now()
    audit.record(
        db,
        "release.activated",
        actor_id=actor,
        target_type="release",
        target_id=str(release.id),
        detail={
            "ontologyId": str(ontology.id),
            "version": release.version,
            "previousReleaseId": str(previous) if previous else None,
            "bindingCount": release.binding_count,
        },
        ip=ip,
    )
    await db.commit()
    return _release_out(release, release.id)
