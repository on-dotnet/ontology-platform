"""Importing OWL files: into a new ontology, or into an existing one as a change set (spec 002,
4.1 and 5).

The file is read into an `OntologyState`, compared with the working version, and the
differences become a change set with source `import`. Nothing is applied until the change set
is reviewed and merged: imports write through change sets like every other source.
"""

import asyncio
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from pathlib import PurePath
from typing import Any, cast
from uuid import UUID, uuid4

from rdflib.namespace import DCTERMS
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.ontology import rules, schemas, service
from ontology_platform.modules.ontology.models import KINDS, Element, Kind, Ontology
from ontology_platform.modules.ontology.rdf import reader, writer
from ontology_platform.modules.ontology.rdf.diff import KIND_FIELDS, Change, diff, keep_lost_lists
from ontology_platform.modules.ontology.rdf.model import ElementState, OntologyState
from ontology_platform.modules.ontology.rdf.reader import RdfInputError
from ontology_platform.modules.ontology.turtle import OntologyHeader, rule_fields, to_state

MAX_BYTES = reader.MAX_BYTES
_STATUS = {
    "import.too_large": 413,
    "import.unsupported_format": 415,
    "import.parse_error": 422,
    "import.too_many_triples": 422,
    "import.empty": 422,
}
_OP_ORDER = {"create": 0, "restore": 1, "update": 2, "delete": 3}
_REF_KEYS = {
    "parent": "parentRef",
    "domain": "domainRef",
    "range": "rangeRef",
    "inverse": "inverseRef",
}
_LOCAL_TAIL = re.compile(r"[^A-Za-z0-9]")


class ImportParseError(AppError):
    """422 `import.parse_error`, with the line where the file stopped being valid."""

    def __init__(self, detail: str, line: int | None) -> None:
        super().__init__(422, "import.parse_error", detail)
        self.line = line

    def body(self) -> dict[str, Any]:
        return {
            "type": "about:blank",
            "title": HTTPStatus(self.status).phrase,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
            "line": self.line,
            "column": None,
        }


def _parse(data: bytes) -> Any:
    try:
        return reader.parse_document(data)
    except RdfInputError as error:
        if error.code == "import.parse_error":
            raise ImportParseError(error.detail, error.line) from error
        raise AppError(_STATUS[error.code], error.code, error.detail) from error


def _merged_prefixes(header: OntologyHeader, incoming: Mapping[str, str]) -> dict[str, str]:
    """Stored prefixes plus new ones. A namespace keeps the one name it already has, so that
    axiom fragments written earlier always parse with the export's prefixes."""
    stored = dict(header.prefixes)
    current = header.prefix_map()
    names, namespaces = set(current), set(current.values())
    for name, namespace in sorted(incoming.items()):
        if not writer.valid_prefix_name(name) or name in names or namespace in namespaces:
            continue
        stored[name] = namespace
        names.add(name)
        namespaces.add(namespace)
    return stored


def _local_name(iri: str, used: set[str]) -> str:
    tail = re.split(r"[#/:]", iri.rstrip("#/:"))[-1]
    name = _LOCAL_TAIL.sub("", tail)[:100] or "element"
    if not name[0].isalpha():
        name = "x" + name
    candidate, number = name, 2
    while candidate in used:
        candidate = f"{name}{number}"
        number += 1
    used.add(candidate)
    return candidate


class _Proposals:
    """Change items for a diff; references become element ids or temp_refs of creates."""

    def __init__(
        self,
        existing: Mapping[str, Element],
        axioms: Mapping[str, Element],
        local_names: set[str],
        prefixes: Mapping[str, str],
        changes: Sequence[Change],
    ) -> None:
        self.existing = existing
        self.axioms = axioms
        self.used = set(local_names)
        self.prefixes = prefixes
        self.refs: dict[str, str] = {iri: str(element.id) for iri, element in existing.items()}
        creates = [c.element for c in changes if c.op == "create" and c.element is not None]
        for number, created in enumerate(creates, start=1):
            self.refs[created.iri] = f"new:{number}"

    def fields(self, element: ElementState, names: Sequence[str]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name in names:
            value = getattr(element, name)
            if name in _REF_KEYS:
                data[_REF_KEYS[name]] = self.refs.get(value) if value else None
            elif name == "synonyms":
                data["synonyms"] = [{"lang": lang, "text": text} for lang, text in value]
            elif name == "rules":
                data["rules"] = [rule_fields(rule, self.refs) for rule in value]
            else:
                data[rules.wire_name(name)] = value
        return data

    def item(self, change: Change) -> schemas.ProposedItem:
        kind = cast(Kind, change.kind)  # the RDF layer uses the platform's kinds
        if change.axiom is not None:
            if change.op == "create":
                return schemas.ProposedItem(
                    op="create",
                    kind="axiom",
                    proposed=schemas.ElementFields(
                        turtle=writer.fragment(change.axiom.triples, self.prefixes),
                    ),
                    flags=["non_standard"] if change.axiom.non_standard else [],
                )
            target = self.axioms[str(change.axiom.id)]
            return schemas.ProposedItem(
                op="delete",
                kind="axiom",
                target_element_id=target.id,
                target_revision=target.revision,
                proposed=schemas.ElementFields(),
            )
        element = change.element
        if element is None:
            raise ValueError("an element change without an element")
        applicable = KIND_FIELDS[element.kind]
        if change.op == "create":
            data = self.fields(element, applicable)
            data["iri"] = element.iri
            data["localName"] = _local_name(element.iri, self.used)
            return schemas.ProposedItem(
                op="create",
                kind=kind,
                temp_ref=self.refs[element.iri],
                proposed=schemas.ElementFields.model_validate(data),
            )
        target = self.existing[element.iri]
        if change.op == "delete":
            proposed = schemas.ElementFields()
        else:
            changed = [name for name in applicable if name in change.fields]
            proposed = schemas.ElementFields.model_validate(self.fields(element, changed))
        return schemas.ProposedItem(
            op=change.op,
            kind=kind,
            target_element_id=target.id,
            target_revision=target.revision,
            proposed=proposed,
        )


def _sort_key(item: schemas.ProposedItem) -> tuple[int, int, str]:
    label = item.proposed.local_name or item.proposed.turtle or str(item.target_element_id)
    return (KINDS.index(item.kind), _OP_ORDER[item.op], label)


def _counts(items: Sequence[schemas.ProposedItem]) -> schemas.ImportCounts:
    ops = Counter(item.op for item in items)
    return schemas.ImportCounts(
        create=ops["create"],
        update=ops["update"],
        delete=ops["delete"],
        restore=ops["restore"],
    )


def _warnings(found: Counter[str]) -> list[schemas.ImportWarning]:
    codes = ("non_standard", "multiple_parents", "unsupported_shape", "lost_list")
    return [
        schemas.ImportWarning(code=code, count=found[code])  # type: ignore[arg-type]
        for code in codes
        if found[code] > 0
    ]


async def _propose(
    db: AsyncSession,
    ontology: Ontology,
    elements: Sequence[Element],
    current: OntologyState,
    target: OntologyState,
    *,
    filename: str,
    actor: UUID,
) -> tuple[UUID | None, list[schemas.ProposedItem]]:
    header = service.header_of(ontology)
    existing: dict[str, Element] = {}
    for element in elements:
        iri = service.iri_of(element, ontology.base_iri)
        if iri is not None and element.kind != "axiom":
            existing[iri] = element
    axioms = {str(element.id): element for element in elements if element.kind == "axiom"}
    changes = diff(current, target).changes
    proposals = _Proposals(
        existing,
        axioms,
        {element.local_name for element in elements if element.local_name},
        header.prefix_map(),
        changes,
    )
    items = sorted((proposals.item(change) for change in changes), key=_sort_key)
    if not items:
        return None, items
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology.id,
        title=f"导入：{filename}"[: service.TITLE_MAX_LENGTH],
        source="import",
        document_id=None,
        created_by=actor,
        items=items,
    )
    return change_set_id, items


def _stem(filename: str) -> str:
    return PurePath(filename).stem.strip()


async def import_new(
    db: AsyncSession,
    *,
    data: bytes,
    filename: str,
    name: str | None,
    key: str | None,
    actor: UUID,
    ip: str | None,
) -> schemas.ImportResult:
    """Create an ontology from a file; its content arrives as an import change set."""
    graph = await asyncio.to_thread(_parse, data)
    result = await asyncio.to_thread(reader.read, graph)
    title = (name or result.state.name or _stem(filename) or "Imported ontology").strip()[:200]
    body = schemas.OntologyCreate(
        name=title,
        key=key,
        description=result.state.description,
    )
    chosen = await service._choose_key(db, body)
    base = result.base_iri if result.base_iri and len(result.base_iri) <= 512 else None
    now = service._now()
    ontology = Ontology(
        id=uuid4(),
        key=chosen,
        name=body.name,
        description=rules.clean_text(body.description),
        base_iri=base or service.default_base_iri(chosen),
        ontology_iri=result.file_ontology_iri,
        prefixes={},
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    ontology.prefixes = _merged_prefixes(service.header_of(ontology), result.prefixes)
    db.add(ontology)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "ontology.key_taken", "The ontology key is already in use.") from exc
    target = result.state
    target.ontology_iri = service.header_of(ontology).ontology_iri
    current = OntologyState(ontology_iri=target.ontology_iri)
    change_set_id, items = await _propose(
        db,
        ontology,
        [],
        current,
        target,
        filename=filename,
        actor=actor,
    )
    for action in ("ontology.created", "ontology.imported"):
        audit.record(
            db,
            action,
            actor_id=actor,
            target_type="ontology",
            target_id=str(ontology.id),
            detail={"key": chosen, "name": ontology.name, "items": len(items)},
            ip=ip,
        )
    await db.commit()
    return schemas.ImportResult(
        ontology=await service.get_ontology_summary(db, ontology.id),
        change_set_id=change_set_id,
        counts=_counts(items),
        warnings=_warnings(result.warnings),
    )


async def import_into(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    data: bytes,
    filename: str,
    actor: UUID,
    ip: str | None,
) -> schemas.ImportResult:
    """Compare a file with the working version; the differences become an import change set."""
    ontology = await service._ontology_or_404(db, ontology_id)
    graph = await asyncio.to_thread(_parse, data)
    header = service.header_of(ontology)
    result = await asyncio.to_thread(
        reader.read,
        graph,
        ontology_iri=header.ontology_iri,
        absorb={DCTERMS.created: writer.created_literal(ontology.created_at)},
    )
    ontology.prefixes = _merged_prefixes(header, result.prefixes)
    elements = await service._elements(db, ontology.id)
    current = to_state(
        service.header_of(ontology),
        [service.element_out(element, ontology.base_iri) for element in elements],
        include_deleted=True,
    )
    found = Counter(result.warnings)
    restored = keep_lost_lists(current, result.state)
    found["lost_list"] = max(0, found["lost_list"] - restored)
    change_set_id, items = await _propose(
        db,
        ontology,
        elements,
        current,
        result.state,
        filename=filename,
        actor=actor,
    )
    audit.record(
        db,
        "ontology.imported",
        actor_id=actor,
        target_type="ontology",
        target_id=str(ontology.id),
        detail={"changeSetId": str(change_set_id) if change_set_id else None, "items": len(items)},
        ip=ip,
    )
    await db.commit()
    return schemas.ImportResult(
        ontology=await service.get_ontology_summary(db, ontology.id),
        change_set_id=change_set_id,
        counts=_counts(items),
        warnings=_warnings(found),
    )
