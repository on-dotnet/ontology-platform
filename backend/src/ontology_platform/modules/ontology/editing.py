"""Manual edits and impact analysis (spec 002, sections 6 and 9).

Every manual save becomes a change set with source `manual`, the platform's only write path.
`apply` merges it at once for users who may review their own changes; any item that would be
skipped rolls the whole save back, so a failed save leaves nothing behind.

Deletes bring their cascade along. It is computed on the ontology as the save's own updates
leave it, so that a reference the user moves away in the same save is not cleared again, and a
save that keeps or adds a reference to something it deletes is refused instead of half applied.
"""

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology import expert, rules, schemas, service
from ontology_platform.modules.ontology.models import Element, Kind, Ontology
from ontology_platform.modules.ontology.rdf.reader import RdfInputError

# Reference keys of item fields and the columns they set.
_REF_COLUMNS = {
    "parent_ref": "parent_id",
    "domain_ref": "domain_id",
    "range_ref": "range_id",
    "inverse_ref": "inverse_id",
}


def _not_found() -> AppError:
    return AppError(404, "element.not_found", "Element not found.")


def _invalid(seq: int, problem: str) -> AppError:
    return AppError(422, "changeset.invalid_edit", f"Item {seq}: {problem}.")


class CascadeConflictError(AppError):
    """An item keeps, adds or edits what a delete of the same save removes."""

    def __init__(self, seq: int, problem: str) -> None:
        super().__init__(422, "changeset.invalid_edit", f"Item {seq}: {problem}.")
        self.seq = seq


@dataclass
class _View:
    """What the cascade needs of an element, possibly as the save's updates leave it."""

    id: UUID
    kind: str
    status: str
    revision: int
    label: str
    iri: str | None
    turtle: str | None
    subject_id: UUID | None
    parent_id: UUID | None = None
    domain_id: UUID | None = None
    range_id: UUID | None = None
    inverse_id: UUID | None = None
    rules: list[dict[str, Any]] = field(default_factory=list)

    def refs(self) -> set[UUID]:
        columns = (self.parent_id, self.domain_id, self.range_id, self.inverse_id)
        found = {ref for ref in columns if ref is not None}
        for rule in self.rules:
            found |= _rule_ids(rule)
        return found


def _rule_ids(rule: Mapping[str, Any]) -> set[UUID]:
    """The elements a stored rule points to: its path and its class."""
    found: set[UUID] = set()
    for key in ("pathId", "classId"):
        ref = rules.parse_id(str(rule[key])) if rule.get(key) else None
        if ref is not None:
            found.add(ref)
    return found


def _label(element: Element) -> str:
    if element.kind == "axiom":
        return (element.turtle or "").strip().partition("\n")[0][:120]
    return rules.display_label(element.label_zh, element.label_en, element.local_name)


def _views(ontology: Ontology, elements: Iterable[Element]) -> dict[UUID, _View]:
    return {
        e.id: _View(
            id=e.id,
            kind=e.kind,
            status=e.status,
            revision=e.revision,
            label=_label(e),
            iri=service.iri_of(e, ontology.base_iri),
            turtle=e.turtle,
            subject_id=e.subject_id,
            parent_id=e.parent_id,
            domain_id=e.domain_id,
            range_id=e.range_id,
            inverse_id=e.inverse_id,
            rules=list(e.rules or []),
        )
        for e in elements
    }


def _ref_id(value: str | None) -> UUID | None:
    """An element id; None for no reference and for the temp_ref of an item created now."""
    return rules.parse_id(value) if value else None


def _stored_rule(rule: schemas.ConstraintRuleFields) -> dict[str, Any]:
    data = rule.model_dump(by_alias=True, exclude_none=True)
    data["pathId"] = data.pop("pathRef", None)
    data["classId"] = data.pop("classRef", None)
    return data


def _with_fields(
    view: _View,
    op: str,
    fields: schemas.ElementFields,
    prefixes: Mapping[str, str],
    subjects: Mapping[str, UUID],
) -> _View:
    """The view after an update or restore with `fields`. `subjects` maps the IRIs of the
    elements an axiom can be about to their ids."""
    given = fields.model_fields_set
    changes: dict[str, Any] = {}
    for key, column in _REF_COLUMNS.items():
        if key in given:
            changes[column] = _ref_id(getattr(fields, key))
    if "rules" in given and fields.rules is not None:
        changes["rules"] = [_stored_rule(rule) for rule in fields.rules]
    if view.kind == "axiom" and fields.turtle is not None:
        changes["turtle"] = fields.turtle
        # The old subject must stop pulling the axiom into the cascade. The new one needs no
        # binding here: a subject is always mentioned, and mentions are read from the fragment.
        try:
            subject = service.normalize_axiom(fields.turtle, prefixes).subject
        except RdfInputError:
            subject = None
        changes["subject_id"] = subjects.get(subject) if subject is not None else None
    if op == "restore":
        changes["status"] = "active"
    return replace(view, **changes)


def _field_refs(fields: schemas.ElementFields) -> set[UUID]:
    """Existing elements the fields refer to."""
    found = {
        ref
        for key in _REF_COLUMNS
        if key in fields.model_fields_set and (ref := _ref_id(getattr(fields, key))) is not None
    }
    for rule in fields.rules or []:
        for value in (rule.path_ref, rule.class_ref):
            ref = _ref_id(value)
            if ref is not None:
                found.add(ref)
    return found


def _mentioned_iris(fields: schemas.ElementFields, prefixes: Mapping[str, str]) -> frozenset[str]:
    """The IRIs an axiom fragment of the fields mentions, as the cascade reads stored axioms."""
    if not fields.turtle:
        return frozenset()
    try:
        return service.normalize_axiom(fields.turtle, prefixes).mentions
    except RdfInputError:
        # Saves check fragments before the cascade; one that does not parse mentions nothing.
        return frozenset()


class _Cascade:
    """Who refers to whom, and what deleting some elements does to the others."""

    def __init__(self, views: Mapping[UUID, _View], prefixes: Mapping[str, str]) -> None:
        self.views = views
        self.incoming: defaultdict[UUID, list[_View]] = defaultdict(list)
        by_iri = {view.iri: view.id for view in views.values() if view.iri}
        for view in views.values():
            if view.status != "active":
                continue
            ids = view.refs()
            if view.subject_id is not None:
                ids.add(view.subject_id)
            if view.kind == "axiom" and view.turtle:
                try:
                    mentions = service.normalize_axiom(view.turtle, prefixes).mentions
                except RdfInputError:
                    # A stored axiom always parses; if one does not, it mentions nothing usable.
                    mentions = frozenset()
                ids.update(by_iri[iri] for iri in mentions if iri in by_iri)
            for ref in ids:
                self.incoming[ref].append(view)

    def changes(self, roots: Iterable[UUID]) -> dict[UUID, schemas.ElementFields | None]:
        """Element id → fields to update it with, or None to delete it, for deleting `roots`.

        Relations and properties defined on a deleted element, constraints targeting one, and
        axioms mentioning one go too (and in turn take their own dependents); subtypes, inverse
        relations and other constraints let go of it.
        """
        leaving = set(roots)
        queue = deque(leaving)
        changes: dict[UUID, schemas.ElementFields | None] = {}
        while queue:
            target = queue.popleft()
            for view in self.incoming[target]:
                if view.id in leaving:
                    continue
                fields: schemas.ElementFields | None = None
                if view.kind == "entity_type":
                    fields = schemas.ElementFields(parent_ref=None)
                elif view.kind == "relation_type" and target not in (view.domain_id, view.range_id):
                    fields = schemas.ElementFields(inverse_ref=None)
                elif view.kind == "constraint" and view.domain_id not in leaving:
                    # An empty rule list is a valid constraint: removing rules never deletes it.
                    kept = [
                        service.stored_rule_fields(rule)
                        for rule in view.rules
                        if not (_rule_ids(rule) & leaving)
                    ]
                    fields = schemas.ElementFields.model_validate({"rules": kept})
                changes[view.id] = fields
                if fields is None:
                    leaving.add(view.id)
                    queue.append(view.id)
        return changes


def cascade_items(
    ontology: Ontology,
    elements: Sequence[Element],
    targets: Sequence[Element],
) -> list[schemas.ProposedItem]:
    """The items that go with deleting `targets` (spec 002, section 6), computed together so
    that a constraint losing rules to several of them is updated once. The ontology's prefixes
    are needed to read which IRIs stored axioms mention."""
    views = _views(ontology, elements)
    changes = _Cascade(views, service.header_of(ontology).prefix_map()).changes(
        target.id for target in targets
    )
    return [_cascade_item(views[element_id], fields) for element_id, fields in changes.items()]


def _cascade_item(view: _View, fields: schemas.ElementFields | None) -> schemas.ProposedItem:
    return schemas.ProposedItem(
        op="delete" if fields is None else "update",
        kind=cast(Kind, view.kind),
        target_element_id=view.id,
        target_revision=view.revision,
        proposed=fields or schemas.ElementFields(),
    )


def _ref(view: _View) -> schemas.ElementRef:
    return schemas.ElementRef(
        id=view.id, kind=cast(Kind, view.kind), label=view.label, iri=view.iri
    )


async def impact(db: AsyncSession, ontology_id: UUID, element_id: UUID) -> schemas.Impact:
    """Active elements that refer to the element, and what deleting it would change."""
    ontology = await service._ontology_or_404(db, ontology_id)
    views = _views(ontology, await service._elements(db, ontology_id))
    target = views.get(element_id)
    if target is None:
        raise _not_found()
    graph = _Cascade(views, service.header_of(ontology).prefix_map())

    inverse = views.get(target.inverse_id) if target.inverse_id else None
    if inverse is not None and inverse.status != "active":
        inverse = None
    groups: defaultdict[str, list[schemas.ElementRef]] = defaultdict(list)
    for view in sorted(graph.incoming[target.id], key=lambda v: (v.label, str(v.id))):
        if view.kind == "relation_type":
            if inverse is None and view.inverse_id == target.id:
                inverse = view
            if target.id not in (view.domain_id, view.range_id):
                continue
        groups[view.kind].append(_ref(view))
    changes = graph.changes([target.id])
    cascade = [
        schemas.CascadeChange(op="delete" if fields is None else "update", element=_ref(views[id_]))
        for id_, fields in sorted(
            changes.items(), key=lambda pair: (views[pair[0]].label, str(pair[0]))
        )
    ]
    return schemas.Impact(
        element_id=element_id,
        subtypes=groups["entity_type"],
        relations=groups["relation_type"],
        properties=groups["property"],
        constraints=groups["constraint"],
        axioms=groups["axiom"],
        inverse=_ref(inverse) if inverse is not None else None,
        cascade=cascade,
    )


@dataclass
class _Checked:
    """The user's items, checked, with the targets they name."""

    items: list[schemas.ProposedItem] = field(default_factory=list)
    targets: dict[UUID, int] = field(default_factory=dict)  # element id → item index
    deletes: list[UUID] = field(default_factory=list)


async def _check_items(
    db: AsyncSession,
    ontology: Ontology,
    elements: Sequence[Element],
    body: schemas.EditRequest,
) -> _Checked:
    by_id = {e.id: e for e in elements}
    names = {e.local_name for e in elements if e.local_name}
    iris = {service.iri_of(e, ontology.base_iri) for e in elements}
    axioms: dict[str, int] = {}
    checked = _Checked()
    for seq, edit in enumerate(body.items, start=1):
        fields = edit.fields
        target = by_id.get(edit.target_element_id) if edit.target_element_id else None
        if edit.op != "create":
            if target is None or target.kind != edit.kind:
                raise _not_found()
            if target.id in checked.targets:
                first = checked.targets[target.id] + 1
                raise _invalid(seq, f"item {first} already changes this element")
            status = "deprecated" if edit.op == "restore" else "active"
            if target.revision != edit.target_revision or target.status != status:
                raise AppError(409, "element.stale", f"Item {seq}: the element has changed.")
            checked.targets[target.id] = len(checked.items)
            if edit.op == "delete":
                checked.deletes.append(target.id)
        elif fields.iri is not None:
            # An explicit IRI marks an imported element, which skips the naming rules.
            raise _invalid(seq, "iri is set by imports only")
        problems = rules.field_problems(
            edit.kind,
            edit.op,
            fields,
            target_local_name=target.local_name if target else None,
            target_imported=target is not None and target.iri is not None,
        )
        if problems:
            raise _invalid(seq, ", ".join(problems))
        if edit.op == "create" and fields.local_name is not None:
            iri = ontology.base_iri + fields.local_name
            if fields.local_name in names or iri in iris:
                raise AppError(409, "element.name_taken", f"Item {seq}: the name is in use.")
            names.add(fields.local_name)
            iris.add(iri)
        if edit.kind == "axiom" and edit.op != "delete":
            turtle = fields.turtle or (target.turtle if target else None)
            if turtle is None:
                raise AppError(422, "axiom.invalid", f"Item {seq}: the fragment is missing.")
            # A restore is checked too: the ontology may have changed since the axiom left it.
            axiom = await expert.check_axiom(db, ontology, turtle, replacing=edit.target_element_id)
            if axiom.turtle in axioms:
                raise AppError(
                    422,
                    "axiom.invalid",
                    f"Item {seq}: item {axioms[axiom.turtle]} adds the same axiom.",
                )
            axioms[axiom.turtle] = seq
            fields = fields.model_copy(update={"turtle": axiom.turtle})
        checked.items.append(
            schemas.ProposedItem(
                op=edit.op,
                kind=edit.kind,
                target_element_id=edit.target_element_id,
                target_revision=edit.target_revision,
                temp_ref=edit.temp_ref,
                proposed=fields,
            ),
        )
    return checked


def _add_cascade(ontology: Ontology, elements: Sequence[Element], checked: _Checked) -> None:
    """Append the cascade of the save's deletes, computed on the ontology as its updates leave
    it, and refuse a save that keeps or adds a reference to what it deletes."""
    views = _views(ontology, elements)
    prefixes = service.header_of(ontology).prefix_map()
    subjects = {
        view.iri: view.id
        for view in views.values()
        if view.iri and view.kind != "axiom" and view.status == "active"
    }
    for item in checked.items:
        if item.op in ("update", "restore") and item.target_element_id is not None:
            view = views[item.target_element_id]
            views[view.id] = _with_fields(view, item.op, item.proposed, prefixes, subjects)
    changes = _Cascade(views, prefixes).changes(checked.deletes)
    leaving = set(checked.deletes) | {id_ for id_, fields in changes.items() if fields is None}
    leaving_iris = {iri for id_ in leaving if (iri := views[id_].iri)}
    for seq, item in enumerate(checked.items, start=1):
        if item.op == "delete":
            continue
        # A new axiom is no row yet, so the cascade cannot see what it mentions: read its fragment.
        mentioned = _mentioned_iris(item.proposed, prefixes)
        if _field_refs(item.proposed) & leaving or mentioned & leaving_iris:
            raise CascadeConflictError(seq, "it refers to an element this save deletes")
        if item.target_element_id in leaving:
            raise CascadeConflictError(
                seq, "another item of this save deletes this element along with its own"
            )
    for element_id, fields in changes.items():
        index = checked.targets.get(element_id)
        if index is None:
            checked.items.append(_cascade_item(views[element_id], fields))
            continue
        # The user's own update of the element: their values stand, the cascade adds the rest.
        own = checked.items[index]
        cascaded = rules.stored_fields(fields) if fields is not None else {}
        own.proposed = rules.effective_fields(cascaded, rules.stored_fields(own.proposed))


def _title(elements: Mapping[UUID, Element], checked: _Checked, count: int) -> str:
    first = checked.items[0]
    target = elements.get(first.target_element_id) if first.target_element_id else None
    if target is not None:
        name = _label(target)
    elif first.kind == "axiom":
        name = (first.proposed.turtle or "").strip().partition("\n")[0]
    else:
        fields = first.proposed
        name = rules.display_label(fields.label_zh, fields.label_en, fields.local_name)
    name = name[:40]
    return f"手工修改：{name}" if count == 1 else f"手工修改：{name} 等 {count} 项"


async def save_edits(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.EditRequest,
    *,
    actor: UUID,
    may_apply: bool,
    ip: str | None,
) -> schemas.EditResult:
    """Save `body.items` as a manual change set; merge it when `body.apply` and `may_apply`."""
    ontology = await service._ontology_or_404(db, ontology_id, lock=True)
    elements = await service._elements(db, ontology_id)
    checked = await _check_items(db, ontology, elements, body)
    own_count = len(checked.items)
    if checked.deletes:
        _add_cascade(ontology, elements, checked)
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology_id,
        title=_title({e.id: e for e in elements}, checked, len(checked.items)),
        source="manual",
        document_id=None,
        created_by=actor,
        items=checked.items,
    )
    merge = None
    if body.apply and may_apply:
        change_set = await service._change_set_or_404(db, change_set_id, lock=True)
        now = service._now()
        rows = await service._items(db, change_set)
        for row in rows:
            service._decide(row, "accepted", actor, now)
        merge = await service._apply_change_set(db, change_set, ontology, actor=actor, ip=ip)
        if merge.skipped:
            # Read the rows before the rollback expires them.
            error = _skipped(merge.skipped, rows, own_count)
            await db.rollback()
            raise error
    await db.commit()
    return schemas.EditResult(change_set_id=change_set_id, merged=merge is not None, merge=merge)


def _skipped(
    skipped: Sequence[schemas.MergeSkip],
    rows: Sequence[Any],
    own_count: int,
) -> AppError:
    """409 for a save that would have been applied in part, naming the root cause: a skip for a
    skipped dependency only follows another one."""
    skip = next((s for s in skipped if s.code != service.DEPENDENCY_SKIPPED), skipped[0])
    code = "element.stale" if skip.code == service.STALE_TARGET else skip.code
    seq = next(row.seq for row in rows if row.id == skip.item_id)
    where = f"Item {seq}" if seq <= own_count else "A change the deletion brings along"
    return AppError(409, code, f"{where} could not be applied ({skip.code}).")
