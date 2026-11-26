"""Business terms from the active release for question planning."""

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.documents import service as documents
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.models import ChangeItem, ChangeSet, Evidence, Ontology
from ontology_platform.modules.ontology.schemas import ElementCopy

_PREFIX = {"entity_type": "T", "property": "P", "relation_type": "R", "metric": "M"}


@dataclass(frozen=True, slots=True)
class QaContext:
    text: str
    refs: Mapping[str, UUID]
    ontology: bindings.ReleasedOntology
    model: bindings.BoundModel
    metrics: bindings.ReleasedMetrics


def metric_is_bound(metric: bindings.MetricCopy, model: bindings.BoundModel) -> bool:
    subject = model.type(metric.subject_id)
    if subject is None:
        return False
    definition = metric.metric
    needed = {f.property_id for f in (*definition.filters, *definition.numerator)}
    if definition.property_id is not None:
        needed.add(definition.property_id)
    return needed.issubset(p.property_id for p in subject.properties)


def _choices(elements: tuple[ElementCopy, ...]) -> dict[tuple[UUID, UUID], list[str]]:
    choices: dict[tuple[UUID, UUID], list[str]] = {}
    for shape in elements:
        if shape.kind != "constraint" or shape.domain_id is None:
            continue
        for rule in shape.rules or ():
            if rule.allowed_values is None or rule.allowed_values_lost:
                continue
            key = (shape.domain_id, rule.path_id)
            values = dict.fromkeys(
                v.lexical if v.lexical is not None else v.iri for v in rule.allowed_values
            )
            # Each independent sh:in applies to the same property of the same target class.
            choices[key] = (
                [v for v in choices[key] if v in values]
                if key in choices
                else [v for v in values if v is not None]
            )
    return choices


def _context(
    ontology: bindings.ReleasedOntology,
    model: bindings.BoundModel,
    metrics: bindings.ReleasedMetrics,
) -> QaContext:
    bound = {t.type_id for t in model.types}
    bound.update(p.property_id for t in model.types for p in t.properties)
    bound.update(r.relation_id for r in model.relations)
    bound.update(r.inverse_id for r in model.relations if r.inverse_id is not None)
    bound.update(m.id for m in metrics.metrics if metric_is_bound(m, model))
    entries: list[tuple[str, ElementCopy | bindings.MetricCopy]] = [
        (e.kind, e) for e in ontology.elements if e.kind in _PREFIX
    ]
    entries.extend(("metric", m) for m in metrics.metrics)
    # Stable tie breakers keep short references reproducible across equivalent releases.
    entries.sort(
        key=lambda pair: (
            pair[1].id not in bound,
            pair[0],
            pair[1].label_zh or pair[1].label_en or pair[1].local_name or "",
            pair[1].local_name or "",
            pair[1].id,
        )
    )
    entries = entries[:400]
    counts: Counter[str] = Counter()
    refs: dict[UUID, str] = {}
    for kind, entry in entries:
        counts[kind] += 1
        refs[entry.id] = f"{_PREFIX[kind]}{counts[kind]}"

    choices = _choices(ontology.elements)
    rows = []
    for kind, entry in entries:
        row: dict[str, object] = {"ref": refs[entry.id], "kind": kind}
        if isinstance(entry, bindings.MetricCopy):
            definition = entry.definition_zh or entry.definition_en
            row.update(
                labelZh=entry.label_zh,
                definition=definition[:200] if definition else None,
                subject=refs.get(entry.subject_id),
                aggregate=entry.metric.aggregate,
            )
        else:
            row["labelZh"] = entry.label_zh
            row["labelEn"] = entry.label_en or (entry.local_name if not entry.label_zh else None)
            row["bound"] = entry.id in bound
            domain = refs.get(entry.domain_id) if entry.domain_id is not None else None
            if kind == "entity_type":
                definition = entry.definition_zh or entry.definition_en
                row.update(
                    definition=definition[:200] if definition else None,
                    parent=refs.get(entry.parent_id) if entry.parent_id else None,
                )
            elif kind == "property":
                values = choices.get((entry.domain_id, entry.id), []) if entry.domain_id else []
                row.update(
                    domain=domain,
                    datatype=entry.datatype,
                    unit=entry.unit,
                    allowedValues=values[:20],
                )
            else:
                row.update(
                    domain=domain, range=refs.get(entry.range_id) if entry.range_id else None
                )
        rows.append(row)
    return QaContext(
        text=json.dumps(rows, ensure_ascii=False),
        refs=MappingProxyType({short: id_ for id_, short in refs.items()}),
        ontology=ontology,
        model=model,
        metrics=metrics,
    )


async def active_release_id(db: AsyncSession, ontology_id: UUID) -> UUID:
    statement = select(Ontology.active_release_id).where(Ontology.id == ontology_id)
    matches = (await db.scalars(statement)).all()
    if not matches:
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    release_id = matches[0]
    if release_id is None:
        raise AppError(409, "query.no_release", "The ontology has no active release.")
    return release_id


async def qa_context(db: AsyncSession, ontology_id: UUID) -> QaContext:
    ontology = await bindings.released_ontology(db, ontology_id)
    if ontology is None:
        raise AppError(409, "query.no_release", "The ontology has no active release.")
    model = await bindings.bound_model(db, ontology_id)
    metrics = await bindings.released_metrics(db, ontology_id)
    if model is None or not ontology.release_id == model.release_id == metrics.release.id:
        raise AppError(409, "query.release_changed", "The active release has changed.")
    return _context(ontology, model, metrics)


class QaDocument(NamedTuple):
    document_id: UUID
    document_name: str
    chunk: int
    quote: str


async def qa_documents(
    db: AsyncSession, context: QaContext, element_ids: Iterable[UUID]
) -> dict[UUID, list[QaDocument]]:
    ids = set(element_ids)
    if not ids:
        return {}
    rank = func.row_number().over(
        partition_by=ChangeItem.applied_element_id,
        order_by=(
            ChangeSet.merged_at,
            ChangeSet.id,
            ChangeItem.seq,
            Evidence.document_id,
            Evidence.chunk_id,
            Evidence.char_start.nulls_last(),
            Evidence.quote,
            Evidence.id,
        ),
    )
    provenance = (
        select(
            ChangeItem.applied_element_id.label("element"),
            Evidence.document_id,
            Evidence.chunk_id,
            Evidence.quote,
            rank.label("rank"),
        )
        .join_from(ChangeItem, ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
        .join(Evidence, Evidence.change_item_id == ChangeItem.id)
        .where(
            ChangeSet.ontology_id == context.ontology.ontology_id,
            ChangeSet.status == "merged",
            ChangeSet.merged_at <= context.ontology.published_at,
            ChangeItem.applied_element_id.in_(ids),
            Evidence.kind == "document",
        )
        .subquery()
    )
    rows = await db.execute(
        select(provenance)
        .where(provenance.c.rank <= 2)
        .order_by(provenance.c.element, provenance.c.rank)
    )
    names: dict[UUID, str] = {}
    sequences: dict[UUID, dict[UUID, int]] = {}
    result: dict[UUID, list[QaDocument]] = {}
    for element_id, document_id, chunk_id, quote, _ in rows:
        if document_id not in sequences:
            sequences[document_id] = {}
            try:
                document = await documents.get(db, document_id)
                if document.ontology_id == context.ontology.ontology_id:
                    names[document_id] = document.filename
                    sequences[document_id] = {
                        c.id: c.seq for c in await documents.list_chunks(db, document_id)
                    }
            except AppError as exc:
                # Historical evidence has no foreign key into the documents module.
                if exc.code != "documents.not_found":
                    raise
        seq = sequences[document_id].get(chunk_id)
        if seq is not None:
            citation = QaDocument(document_id, names[document_id], seq, quote)
            result.setdefault(element_id, []).append(citation)
    return result
