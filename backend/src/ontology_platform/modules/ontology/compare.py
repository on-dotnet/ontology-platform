"""Version comparison (spec 002, section 9): what changed between two releases, or between a
release and the working version, and how much each change can break.

Elements are matched by id: an element keeps its id across versions. Release snapshots made
before M2 lack the M2 fields and are read with their defaults.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology import schemas, service
from ontology_platform.modules.ontology.models import KINDS, Release

type _Rows = dict[str, dict[str, Any]]

_FIELDS = (
    "labelZh",
    "labelEn",
    "definitionZh",
    "definitionEn",
    "synonyms",
    "parentId",
    "domainId",
    "rangeId",
    "inverseId",
    "datatype",
    "unit",
    "required",
    "multiple",
    "autoShape",
    "rules",
    "turtle",
)
_REFERENCES = {"parentId", "domainId", "rangeId", "inverseId"}
_LEVELS: tuple[schemas.ChangeLevel, ...] = ("breaking", "review", "compatible")
_DEFAULTS: dict[str, Any] = {
    "synonyms": [],
    "required": False,
    "multiple": False,
    "autoShape": True,
}


async def _release(db: AsyncSession, ontology_id: UUID, release_id: UUID) -> Release:
    # The snapshot only: the release's Turtle can be megabytes and is not compared.
    release = await db.scalar(
        select(Release).where(Release.id == release_id).options(defer(Release.turtle))
    )
    if release is None or release.ontology_id != ontology_id:
        raise AppError(404, "release.not_found", "Release not found.")
    return release


def _label(row: dict[str, Any]) -> str:
    if row["kind"] == "axiom":
        lines = (row.get("turtle") or "").splitlines()
        return str(lines[0][:120]) if lines else ""
    return str(row.get("labelZh") or row.get("labelEn") or row.get("localName") or "")


def _reference(value: str | None, rows: _Rows) -> dict[str, Any] | None:
    if value is None:
        return None
    target = rows.get(value)
    return {"id": value, "label": _label(target) if target is not None else None}


def _field_changes(element_id: str, left: _Rows, right: _Rows) -> list[schemas.FieldChange]:
    changes = []
    for field in _FIELDS:
        before: Any = left[element_id].get(field, _DEFAULTS.get(field))
        after: Any = right[element_id].get(field, _DEFAULTS.get(field))
        if before == after:
            continue
        if field == "synonyms":
            old_names = {(s["lang"], s["text"]) for s in before}
            new_names = {(s["lang"], s["text"]) for s in after}
            if old_names == new_names:
                continue
        if field in _REFERENCES:
            before, after = _reference(before, left), _reference(after, right)
        changes.append(schemas.FieldChange(field=field, before=before, after=after))
    return changes


def _field_level(change: schemas.FieldChange) -> schemas.ChangeLevel:
    field = change.field
    if field in _REFERENCES or field in {"datatype", "unit"}:
        return "breaking"
    if (field == "required" and change.after) or (field == "multiple" and not change.after):
        return "breaking"
    if field in {"autoShape", "rules", "turtle"}:
        return "review"
    return "compatible"


def _element_change(
    element_id: str, left: _Rows, right: _Rows, published: datetime, base_iri: str
) -> schemas.ElementChange | None:
    change: Literal["added", "removed", "changed", "restored"]
    level: schemas.ChangeLevel
    fields: list[schemas.FieldChange] = []
    if element_id not in right:
        row = left[element_id]
        change = "removed"
        level = "review" if row["kind"] in {"constraint", "axiom"} else "breaking"
    elif element_id not in left:
        row = right[element_id]
        restored = datetime.fromisoformat(row["createdAt"]) < published
        change = "restored" if restored else "added"
        # Bringing a constraint or an axiom back adds its rules again, like a new one.
        level = "review" if row["kind"] in {"constraint", "axiom"} else "compatible"
    else:
        row = right[element_id]
        fields = _field_changes(element_id, left, right)
        if not fields:
            return None
        change = "changed"
        level = min(map(_field_level, fields), key=_LEVELS.index)

    iri = None
    if row["kind"] != "axiom":
        iri = row.get("iri") or base_iri + row["localName"]
    return schemas.ElementChange(
        element_id=UUID(element_id),
        kind=row["kind"],
        label=_label(row),
        iri=iri,
        change=change,
        level=level,
        fields=fields,
    )


async def compare(
    db: AsyncSession,
    ontology_id: UUID,
    from_release: UUID,
    to: UUID | Literal["working"],
) -> schemas.Comparison:
    """Changes from release `from_release` to release `to` or to the working version."""
    ontology = await service._ontology_or_404(db, ontology_id)
    source = await _release(db, ontology_id, from_release)
    source_side = schemas.CompareSide(release_id=source.id, version=source.version)
    left = {row["id"]: row for row in source.snapshot}
    if to == "working":
        target_side = schemas.CompareSide(release_id=None, version=None)
        right = {
            str(element.id): service.element_out(element, ontology.base_iri).model_dump(
                mode="json", by_alias=True
            )
            for element in await service._elements(db, ontology_id, all_kinds=True)
            if element.status == "active"
        }
    elif to == from_release:
        target_side, right = source_side, left
    else:
        target = await _release(db, ontology_id, to)
        target_side = schemas.CompareSide(release_id=target.id, version=target.version)
        right = {row["id"]: row for row in target.snapshot}

    changes = []
    counts = dict.fromkeys(_LEVELS, 0)
    for element_id in left.keys() | right.keys():
        item = _element_change(element_id, left, right, source.created_at, ontology.base_iri)
        if item is not None:
            changes.append(item)
            counts[item.level] += 1
    changes.sort(key=lambda c: (_LEVELS.index(c.level), KINDS.index(c.kind), c.label, c.element_id))
    return schemas.Comparison.model_validate(
        {"from": source_side, "to": target_side, "changes": changes, "counts": counts}
    )
