"""Manual edits and impact analysis (spec 002, sections 6 and 9).

Every manual save becomes a change set with source `manual`, the platform's only write path.
`apply` merges it at once for users who may review their own changes; any item that would be
skipped rolls the whole save back, so a failed save leaves nothing behind.
"""

from collections import defaultdict, deque
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology import expert, rules, schemas, service
from ontology_platform.modules.ontology.models import Element, Kind, Ontology


def _label(element: Element | schemas.ElementFields, axiom_limit: int = 120) -> str:
    if element.turtle is not None:
        return element.turtle.partition("\n")[0][:axiom_limit]
    return rules.display_label(element.label_zh, element.label_en, element.local_name)


def _not_found() -> AppError:
    return AppError(404, "element.not_found", "Element not found.")


class _References:
    """Index direct references once, including IRIs anywhere inside active axioms."""

    def __init__(self, elements: list[Element], ontology: Ontology) -> None:
        self.by_id = {e.id: e for e in elements}
        self.incoming: defaultdict[UUID, list[Element]] = defaultdict(list)
        by_iri = {service.iri_of(e, ontology.base_iri): e.id for e in elements}
        prefixes = service.header_of(ontology).prefix_map()
        for e in elements:
            if e.status != "active":
                continue
            ids = {e.parent_id, e.domain_id, e.range_id, e.inverse_id, e.subject_id}
            ids.update(service._rule_references(e))
            if e.kind == "axiom" and e.turtle:
                mentions = service.normalize_axiom(e.turtle, prefixes).mentions
                ids.update(by_iri[iri] for iri in mentions if iri in by_iri)
            for ref in ids:
                if ref is not None:
                    self.incoming[ref].append(e)

    def cascade(self, roots: list[Element]) -> list[schemas.ProposedItem]:
        leaving = {e.id for e in roots}
        queue = deque(e.id for e in roots)
        changes: dict[UUID, schemas.ElementFields | None] = {}
        while queue:
            target = queue.popleft()
            for e in self.incoming[target]:
                if e.id in leaving:
                    continue
                fields = None
                if e.kind == "entity_type":
                    fields = schemas.ElementFields(parent_ref=None)
                elif e.kind == "relation_type" and target not in (e.domain_id, e.range_id):
                    fields = schemas.ElementFields(inverse_ref=None)
                elif e.kind == "constraint" and e.domain_id not in leaving:
                    kept = [
                        service.stored_rule_fields(rule)
                        for rule in e.rules or []
                        if not any(
                            rules.parse_id(rule[key]) in leaving
                            for key in ("pathId", "classId")
                            if rule.get(key)
                        )
                    ]
                    if kept:
                        fields = schemas.ElementFields.model_validate({"rules": kept})
                changes[e.id] = fields
                if fields is None:
                    leaving.add(e.id)
                    queue.append(e.id)
        items = []
        for element_id, fields in changes.items():
            e = self.by_id[element_id]
            items.append(
                schemas.ProposedItem(
                    op="delete" if fields is None else "update",
                    kind=cast(Kind, e.kind),
                    target_element_id=e.id,
                    target_revision=e.revision,
                    proposed=fields or schemas.ElementFields(),
                )
            )
        return items


def cascade_items(
    ontology: Ontology,
    elements: Sequence[Element],
    targets: Sequence[Element],
) -> list[schemas.ProposedItem]:
    """The items that go with deleting `targets` (spec 002, section 6), computed together so
    that a constraint losing its last rules to several of them is deleted once. Also used by
    the AI assistant (PR C), which adds them to its own deletes. The ontology's prefixes are
    needed to read which IRIs stored axioms mention."""
    return _References(list(elements), ontology).cascade(list(targets))


async def impact(db: AsyncSession, ontology_id: UUID, element_id: UUID) -> schemas.Impact:
    """Active elements that refer to the element."""
    ontology = await service._ontology_or_404(db, ontology_id)
    elements = await service._elements(db, ontology_id)
    target = next((e for e in elements if e.id == element_id), None)
    if target is None:
        raise _not_found()
    references = _References(elements, ontology)

    def ref(e: Element) -> schemas.ElementRef:
        return schemas.ElementRef(
            id=e.id,
            kind=cast(Kind, e.kind),
            label=_label(e),
            iri=service.iri_of(e, ontology.base_iri),
        )

    groups: defaultdict[str, list[schemas.ElementRef]] = defaultdict(list)
    inverse = references.by_id.get(target.inverse_id) if target.inverse_id else None
    if inverse is not None and inverse.status != "active":
        inverse = None
    incoming = sorted(references.incoming[target.id], key=lambda e: (_label(e), e.id))
    for e in incoming:
        if e.kind == "relation_type":
            if inverse is None and e.inverse_id == target.id:
                inverse = e
            if target.id not in (e.domain_id, e.range_id):
                continue
        groups[e.kind].append(ref(e))
    return schemas.Impact(
        element_id=element_id,
        subtypes=groups["entity_type"],
        relations=groups["relation_type"],
        properties=groups["property"],
        constraints=groups["constraint"],
        axioms=groups["axiom"],
        inverse=ref(inverse) if inverse is not None else None,
    )


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
    by_id = {e.id: e for e in elements}
    names = {e.local_name for e in elements if e.local_name}
    iris = {service.iri_of(e, ontology.base_iri) for e in elements}
    items: list[schemas.ProposedItem] = []
    deletes: list[Element] = []
    updates: dict[UUID, int] = {}
    first_name = ""
    for seq, edit in enumerate(body.items, start=1):
        fields = edit.fields
        target = by_id.get(edit.target_element_id) if edit.target_element_id else None
        if edit.op != "create":
            if target is None or target.kind != edit.kind:
                raise _not_found()
            status = "deprecated" if edit.op == "restore" else "active"
            if target.revision != edit.target_revision or target.status != status:
                raise AppError(409, "element.stale", f"Item {seq}: target has changed.")
            if edit.op == "delete":
                deletes.append(target)
            if edit.op == "update":
                updates[target.id] = len(items)
        problems = rules.field_problems(
            edit.kind,
            edit.op,
            fields,
            target_local_name=target.local_name if target else None,
            target_imported=target is not None and target.iri is not None,
        )
        if problems:
            raise AppError(422, "changeset.invalid_edit", f"Item {seq}: {', '.join(problems)}.")
        if edit.op == "create" and fields.local_name is not None:
            iri = fields.iri if fields.iri is not None else ontology.base_iri + fields.local_name
            if fields.local_name in names or iri in iris:
                raise AppError(409, "element.name_taken", f"Item {seq}: name or IRI is in use.")
            names.add(fields.local_name)
            iris.add(iri)
        if edit.kind == "axiom" and edit.op in ("create", "update"):
            turtle = fields.turtle or (target.turtle if target else None)
            if turtle is None:
                raise AppError(422, "axiom.invalid", f"Item {seq}: missing axiom fragment.")
            axiom = await expert.check_axiom(db, ontology, turtle, replacing=edit.target_element_id)
            fields = fields.model_copy(update={"turtle": axiom.turtle})
        if seq == 1:
            first_name = _label(target if target is not None else fields, axiom_limit=40)
        items.append(
            schemas.ProposedItem(
                op=edit.op,
                kind=edit.kind,
                target_element_id=edit.target_element_id,
                target_revision=edit.target_revision,
                temp_ref=edit.temp_ref,
                proposed=fields,
            )
        )

    if deletes:
        for extra in cascade_items(ontology, elements, deletes):
            index = updates.get(extra.target_element_id) if extra.target_element_id else None
            if index is None or extra.op == "delete":
                # Keep an explicit update visible even when a cascade would delete its target.
                # The merge's revision check resolves this conflict like any other stale item.
                items.append(extra)
            else:
                items[index].proposed = rules.effective_fields(
                    rules.stored_fields(items[index].proposed), rules.stored_fields(extra.proposed)
                )
    title = f"手工修改：{first_name}"
    if len(items) > 1:
        title += f" 等 {len(items)} 项"
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology_id,
        title=title,
        source="manual",
        document_id=None,
        created_by=actor,
        items=items,
    )
    merge = None
    if body.apply and may_apply:
        change_set = await service._change_set_or_404(db, change_set_id, lock=True)
        now = service._now()
        rows = await service._items(db, change_set)
        for item in rows:
            service._decide(item, "accepted", actor, now)
        merge = await service.apply_change_set(db, change_set, ontology, actor=actor, ip=ip)
        if merge.skipped:
            skip = merge.skipped[0]
            code = "element.stale" if skip.code == service.STALE_TARGET else skip.code
            position = next(row.seq for row in rows if row.id == skip.item_id)
            detail = f"Item {position} ({skip.item_id}) was skipped ({skip.code})."
            await db.rollback()
            raise AppError(409, code, detail)
    await db.commit()
    return schemas.EditResult(change_set_id=change_set_id, merged=merge is not None, merge=merge)
