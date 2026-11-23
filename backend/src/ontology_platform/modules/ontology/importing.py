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
from dataclasses import dataclass
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
from ontology_platform.modules.ontology.rdf.diff import (
    KIND_FIELDS,
    Change,
    Diff,
    diff,
    keep_lost_lists,
)
from ontology_platform.modules.ontology.rdf.model import ElementState, OntologyState
from ontology_platform.modules.ontology.rdf.reader import RdfInputError
from ontology_platform.modules.ontology.rdf.vocab import FIXED_PREFIXES
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


def _merged_prefixes(
    header: OntologyHeader,
    incoming: Mapping[str, str],
    *,
    new: bool = False,
) -> dict[str, str]:
    """Stored prefixes plus new ones. A namespace keeps the one name it already has, so that
    axiom fragments written earlier always parse with the export's prefixes; only a `new`
    ontology, which has no fragments yet, takes the file's name for its own namespace."""
    stored = dict(header.prefixes)
    current = FIXED_PREFIXES if new else header.prefix_map()
    names, namespaces = set(current), set(current.values())
    for name, namespace in sorted(incoming.items(), key=writer.prefix_order):
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
    """Change items for a diff; references become element ids or temp_refs of creates.

    Elements whose kind the file changed are left alone (spec 002, section 5), so references to
    them are dropped rather than pointed at an element of the wrong kind.
    """

    def __init__(
        self,
        existing: Mapping[str, Element],
        axioms: Mapping[str, Element],
        local_names: set[str],
        prefixes: Mapping[str, str],
        result: Diff,
    ) -> None:
        self.existing = existing
        self.axioms = axioms
        self.used = set(local_names)
        self.prefixes = prefixes
        self.refs: dict[str, str] = {iri: str(element.id) for iri, element in existing.items()}
        for iri in result.kind_changed:
            self.refs.pop(iri, None)
        creates = [c.element for c in result.changes if c.op == "create" and c.element]
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
                data["rules"] = [
                    rule_fields(rule, self.refs)
                    for rule in value
                    if rule.references() <= self.refs.keys()
                ]
            else:
                data[rules.wire_name(name)] = value
        return data

    def item(self, change: Change) -> schemas.ProposedItem:
        kind = cast(Kind, change.kind)  # the RDF layer uses the platform's kinds
        if change.axiom is not None:
            if change.op == "create":
                turtle = writer.fragment(change.axiom.triples, self.prefixes)
                if len(turtle) > schemas.TURTLE_MAX_LENGTH:
                    raise AppError(
                        422,
                        "import.axiom_too_large",
                        "One axiom of the file is longer than the platform keeps.",
                    )
                return schemas.ProposedItem(
                    op="create",
                    kind="axiom",
                    proposed=schemas.ElementFields(turtle=turtle),
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
    codes = ("non_standard", "multiple_parents", "unsupported_shape", "lost_list", "kind_changed")
    return [
        schemas.ImportWarning(code=code, count=found[code])  # type: ignore[arg-type]
        for code in codes
        if found[code] > 0
    ]


@dataclass(slots=True)
class _Proposed:
    change_set_id: UUID | None
    items: list[schemas.ProposedItem]
    kind_changed: int


async def _propose(
    db: AsyncSession,
    ontology: Ontology,
    elements: Sequence[Element],
    current: OntologyState,
    target: OntologyState,
    *,
    filename: str,
    actor: UUID,
) -> _Proposed:
    header = service.header_of(ontology)
    existing: dict[str, Element] = {}
    for element in elements:
        iri = service.iri_of(element, ontology.base_iri)
        if iri is not None and element.kind != "axiom":
            existing[iri] = element
    axioms = {str(element.id): element for element in elements if element.kind == "axiom"}
    result = diff(current, target)
    proposals = _Proposals(
        existing,
        axioms,
        {element.local_name for element in elements if element.local_name},
        header.prefix_map(),
        result,
    )
    items = sorted((proposals.item(change) for change in result.changes), key=_sort_key)
    if not items:
        return _Proposed(None, items, len(result.kind_changed))
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology.id,
        title=f"导入：{filename}"[: service.TITLE_MAX_LENGTH],
        source="import",
        document_id=None,
        created_by=actor,
        items=items,
    )
    return _Proposed(change_set_id, items, len(result.kind_changed))


def _stem(filename: str) -> str:
    return PurePath(filename).stem.strip()


async def _free_key(db: AsyncSession, title: str, key: str | None) -> str:
    """The key the user gave, else one from the name, numbered when the name is taken (the
    same file may well be imported twice)."""
    if key is not None:
        return await service._choose_key(db, schemas.OntologyCreate(name=title, key=key))
    slug = service._slug(title)
    if slug is not None:
        for number in range(1, 100):
            candidate = slug if number == 1 else f"{slug[:58].rstrip('-')}-{number}"
            if not await service._key_taken(db, candidate):
                return candidate
    return await service._choose_key(db, schemas.OntologyCreate(name=title))


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
    # A name the user gave wins; a different name in the file stays as an annotation.
    known = reader.KnownHeader(name=name) if name else None
    result = await asyncio.to_thread(reader.read, graph, known=known)
    title = (name or result.state.name or _stem(filename) or "Imported ontology").strip()[:200]
    description = result.state.description
    chosen = await _free_key(db, title, key)
    base = result.base_iri if result.base_iri and len(result.base_iri) <= 512 else None
    now = service._now()
    ontology = Ontology(
        id=uuid4(),
        key=chosen,
        name=title,
        description=rules.clean_text(description),
        base_iri=base or service.default_base_iri(chosen),
        ontology_iri=result.file_ontology_iri,
        prefixes={},
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    header = service.header_of(ontology)
    if result.file_ontology_iri is None:
        # The file names no ontology: read it again with the IRI the ontology now has, so that
        # annotations of an anonymous header are about this ontology.
        result = await asyncio.to_thread(
            reader.read,
            graph,
            ontology_iri=header.ontology_iri,
            known=known,
        )
    ontology.prefixes = _merged_prefixes(header, result.prefixes, new=True)
    db.add(ontology)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "ontology.key_taken", "The ontology key is already in use.") from exc
    target = result.state
    target.ontology_iri = header.ontology_iri
    proposed = await _propose(
        db,
        ontology,
        [],
        OntologyState(ontology_iri=target.ontology_iri),
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
            detail={"key": chosen, "name": ontology.name, "items": len(proposed.items)},
            ip=ip,
        )
    await db.commit()
    return schemas.ImportResult(
        ontology=await service.get_ontology_summary(db, ontology.id),
        change_set_id=proposed.change_set_id,
        counts=_counts(proposed.items),
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
        known=reader.KnownHeader(ontology.name, ontology.description, strict=True),
    )
    # From here on one import (or merge, or publish) of this ontology at a time: the prefixes
    # the change set's axioms are written with must not change under them.
    ontology = await service._ontology_or_404(db, ontology_id, lock=True)
    ontology.prefixes = _merged_prefixes(service.header_of(ontology), result.prefixes)
    elements = await service._elements(db, ontology.id)
    current = to_state(
        service.header_of(ontology),
        [service.element_out(element, ontology.base_iri) for element in elements],
        include_deleted=True,
    )
    restored = keep_lost_lists(current, result.state)
    proposed = await _propose(
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
        detail={
            "changeSetId": str(proposed.change_set_id) if proposed.change_set_id else None,
            "items": len(proposed.items),
        },
        ip=ip,
    )
    await db.commit()
    # Warnings are about what goes to review; a file that changes nothing needs none.
    found: Counter[str] = Counter()
    if proposed.change_set_id is not None:
        found = Counter(result.warnings)
        found["non_standard"] = sum("non_standard" in item.flags for item in proposed.items)
        found["lost_list"] = max(0, found["lost_list"] - restored)
    found["kind_changed"] = proposed.kind_changed
    return schemas.ImportResult(
        ontology=await service.get_ontology_summary(db, ontology.id),
        change_set_id=proposed.change_set_id,
        counts=_counts(proposed.items),
        warnings=_warnings(found),
    )
