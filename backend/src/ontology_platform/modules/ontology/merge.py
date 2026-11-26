"""Merging a change set into the working version (spec 001 3.4, 002 3.5).

Moved out of service.py. The merge plan (mergeplan.py) and its wiring stay where the
change set views read them too; this module depends on service, never the other way round.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.ontology import binding_rules, mergeplan, rules, schemas
from ontology_platform.modules.ontology.axiom_rules import NormalizedAxiom, normalize_axiom
from ontology_platform.modules.ontology.models import (
    BINDING_KINDS,
    SEMANTIC_KINDS,
    ChangeItem,
    ChangeSet,
    Element,
    Ontology,
)
from ontology_platform.modules.ontology.rdf.reader import RdfInputError
from ontology_platform.modules.ontology.schemas import ReviewMode
from ontology_platform.modules.ontology.service import (
    DEPENDENCY_SKIPPED,
    HAS_DEPENDENTS,
    INVALID_ITEM,
    RESOLUTION_CHANGED,
    STALE_TARGET,
    _change_set_or_404,
    _elements,
    _ensure_not_own,
    _ensure_open,
    _items,
    _links,
    _now,
    _ontology_or_404,
    _plan,
    header_of,
    iri_of,
)


def _rule_references(element: Element) -> set[UUID]:
    found: set[UUID] = set()
    for rule in element.rules or []:
        for key in ("pathId", "classId"):
            value = rule.get(key)
            if value:
                found.add(UUID(str(value)))
    return found


class _Merge:
    """Applies accepted items, each after the items it references.

    The outcome of an item is None when it was applied, otherwise the skip code.
    """

    def __init__(
        self,
        db: AsyncSession,
        change_set: ChangeSet,
        ontology: Ontology,
        elements: Sequence[Element],
        items: Sequence[ChangeItem],
        now: datetime,
        plan: Mapping[UUID, mergeplan.Resolution],
    ) -> None:
        self._db = db
        # Made before anything is applied and followed as it is: what the reviewer was shown.
        self._plan = plan
        self._change_set = change_set
        self._base_iri = ontology.base_iri
        self._prefixes = header_of(ontology).prefix_map()
        self._elements = {element.id: element for element in elements}
        self._local_names = {e.local_name for e in elements if e.local_name}
        self._iris: dict[str, Element] = {}
        for element in elements:
            iri = iri_of(element, self._base_iri)
            if iri is not None:
                self._iris[iri] = element
        self._creates = {item.temp_ref: item for item in items if item.temp_ref is not None}
        self._items = {item.id: item for item in items}
        self._restores = {
            item.target_element_id: item
            for item in items
            if item.op == "restore" and item.target_element_id
        }
        self._visiting: set[UUID] = set()
        # Items whose inverse waits for the item (key) they are paired with to be applied.
        self._deferred: dict[UUID, list[ChangeItem]] = defaultdict(list)
        self._now = now
        # Imported and hand-made synonym lists replace the old ones; AI ones add to them.
        self._replace_synonyms = change_set.source in ("import", "manual")
        self.outcomes: dict[UUID, str | None] = {}

    async def apply(self, item: ChangeItem) -> str | None:
        if item.id in self.outcomes:
            return self.outcomes[item.id]
        self._visiting.add(item.id)
        try:
            outcome = await self._apply(item)
        finally:
            self._visiting.discard(item.id)
        self.outcomes[item.id] = outcome
        # Two relations that name each other as inverse: the one applied first gets its
        # inverse once the other exists.
        for waiting in self._deferred.pop(item.id, []):
            partner = (
                self._elements.get(waiting.applied_element_id)
                if waiting.applied_element_id
                else None
            )
            if outcome is None and partner is not None:
                partner.inverse_id = item.applied_element_id
        return outcome

    def _target(self, item: ChangeItem) -> tuple[str | None, Element | None]:
        target = self._elements.get(item.target_element_id) if item.target_element_id else None
        if target is None or target.kind != item.kind:
            return INVALID_ITEM, None
        if target.revision != item.target_revision:
            return STALE_TARGET, None
        wanted_status = "deprecated" if item.op == "restore" else "active"
        if target.status != wanted_status:
            return INVALID_ITEM, None
        return None, target

    async def _apply(self, item: ChangeItem) -> str | None:
        kind = item.kind
        target: Element | None = None
        resolution = self._plan.get(item.id)
        if resolution is not None and resolution.mode == "update":
            return self._append(item, resolution)
        if item.op in ("update", "restore"):
            problem, target = self._target(item)
            if problem is not None:
                return problem
        fields = rules.effective_fields(item.proposed, item.edited)
        if rules.field_problems(
            kind,
            item.op,
            fields,
            target_local_name=target.local_name if target else None,
            target_imported=target is not None and target.iri is not None,
            target_binding=target.binding if target else None,
        ):
            return INVALID_ITEM
        resolved: dict[str, UUID | None] = {}
        for name in rules.KIND_REFS[kind]:
            if name not in fields.model_fields_set:
                continue
            value = getattr(fields, name)
            if value is None:
                resolved[name] = None
                continue
            outcome, element_id = await self._resolve(
                value,
                rules.ref_targets(kind, name),
                target,
                defer=item if name == "inverse_ref" else None,
            )
            if outcome is not None:
                return outcome
            resolved[name] = element_id
        if kind in BINDING_KINDS:
            return await self._bind(item, target, fields, resolved)
        stored_rules: list[dict[str, Any]] | None = None
        if fields.rules is not None:
            outcome, stored_rules = await self._rules(fields.rules, target)
            if outcome is not None:
                return outcome
        axiom: NormalizedAxiom | None = None
        if kind == "axiom" and fields.turtle is not None:
            try:
                axiom = normalize_axiom(fields.turtle, self._prefixes)
            except RdfInputError:
                return INVALID_ITEM
        if target is None:
            return await self._create(item, fields, resolved, stored_rules, axiom)
        return self._update(item, target, fields, resolved, stored_rules, axiom)

    async def _resolve(
        self,
        value: str,
        kinds: tuple[str, ...],
        own: Element | None,
        *,
        defer: ChangeItem | None = None,
    ) -> tuple[str | None, UUID | None]:
        """The element a reference points at, applying the item that makes it first.

        `defer` (only for inverse relations, which may point at each other) allows a loop: the
        reference resolves to None for now and `apply` fills it in once the partner exists.
        """
        element_id = rules.parse_id(value)
        if element_id is not None:
            element = self._elements.get(element_id)
            if element is None or element.kind not in kinds:
                return INVALID_ITEM, None
            if own is not None and element.id == own.id:
                return INVALID_ITEM, None
            if element.status != "active":
                # A deleted element this change set brings back can be referenced.
                restore = self._restores.get(element.id)
                if restore is None:
                    return INVALID_ITEM, None
                if restore.decision != "accepted":
                    return DEPENDENCY_SKIPPED, None
                if restore.id in self._visiting:
                    if defer is None:
                        return INVALID_ITEM, None
                    self._deferred[restore.id].append(defer)
                    return None, None
                if await self.apply(restore) is not None:
                    return DEPENDENCY_SKIPPED, None
            return None, element.id
        dependency = self._creates.get(value)
        if dependency is None or dependency.kind not in kinds:
            return INVALID_ITEM, None
        if dependency.id in self._visiting:
            if defer is not None and dependency.decision == "accepted":
                self._deferred[dependency.id].append(defer)
                return None, None
            # The items reference each other in a loop.
            return INVALID_ITEM, None
        if dependency.decision != "accepted":
            return DEPENDENCY_SKIPPED, None
        if await self.apply(dependency) is not None:
            return DEPENDENCY_SKIPPED, None
        return None, dependency.applied_element_id

    async def _rules(
        self,
        given: list[schemas.ConstraintRuleFields],
        own: Element | None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        stored: list[dict[str, Any]] = []
        for rule in given:
            data = rule.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
                exclude={"path_ref", "class_ref"},
            )
            outcome, path_id = await self._resolve(rule.path_ref, rules.RULE_PATH_KINDS, own)
            if outcome is not None:
                return outcome, []
            data["pathId"] = str(path_id)
            if rule.class_ref is not None:
                outcome, class_id = await self._resolve(rule.class_ref, ("entity_type",), own)
                if outcome is not None:
                    return outcome, []
                data["classId"] = str(class_id)
            if not data.get("allowedValuesLost"):
                data.pop("allowedValuesLost", None)
            if not data.get("message"):
                data.pop("message", None)
            stored.append(data)
        return None, stored

    async def _bind(
        self,
        item: ChangeItem,
        target: Element | None,
        fields: schemas.ElementFields,
        resolved: dict[str, UUID | None],
    ) -> str | None:
        """Create, change or restore a binding (spec 003, 6.3), checked by the binding rules
        among the elements as the merge has left them so far. The cached catalog is not
        consulted: it may be out of date by now."""
        update = {name: str(value) for name, value in resolved.items() if value is not None}
        node = binding_rules.applied(
            binding_rules.element_node(target) if target is not None else None,
            op=item.op,
            kind=item.kind,
            key=str(target.id) if target is not None else f"item:{item.id}",
            fields=fields.model_copy(update=update),
        )
        nodes = {str(e.id): binding_rules.element_node(e) for e in self._elements.values()}
        if binding_rules.node_problems(node, nodes) or node.binding is None:
            return INVALID_ITEM
        if item.kind == "type_binding" and await binding_rules.data_source_problem(
            self._db, node.binding.get("dataSourceId")
        ):
            return INVALID_ITEM
        if target is not None:
            target.binding = dict(node.binding)
            if item.op == "restore":
                target.status = "active"
            target.revision += 1
            target.updated_at = self._now
            item.applied_element_id = target.id
            return None
        origin = {"manual": "manual", "import": "import"}.get(self._change_set.source, "ai")
        element = Element(
            id=uuid4(),
            ontology_id=self._change_set.ontology_id,
            kind=item.kind,
            local_name=None,
            iri=None,
            label_zh=None,
            synonyms=[],
            subject_id=resolved.get("subject_ref"),
            parent_id=resolved.get("parent_ref"),
            domain_id=resolved.get("domain_ref"),
            range_id=resolved.get("range_ref"),
            binding=dict(node.binding),
            flags=[],
            required=False,
            multiple=False,
            auto_shape=False,
            status="active",
            origin=origin,
            revision=1,
            created_at=self._now,
            updated_at=self._now,
        )
        self._db.add(element)
        await self._db.flush()
        self._elements[element.id] = element
        item.applied_element_id = element.id
        return None

    def _subject_id(self, axiom: NormalizedAxiom) -> UUID | None:
        if axiom.subject is None:
            return None
        element = self._iris.get(axiom.subject)
        if element is None or element.kind not in SEMANTIC_KINDS or element.status != "active":
            return None
        return element.id

    async def _create(
        self,
        item: ChangeItem,
        fields: schemas.ElementFields,
        resolved: dict[str, UUID | None],
        stored_rules: list[dict[str, Any]] | None,
        axiom: NormalizedAxiom | None,
    ) -> str | None:
        kind = item.kind
        origin = {"manual": "manual", "import": "import"}.get(self._change_set.source, "ai")
        if kind == "axiom":
            if axiom is None:
                return INVALID_ITEM
            element = Element(
                id=uuid4(),
                ontology_id=self._change_set.ontology_id,
                kind="axiom",
                local_name=None,
                iri=None,
                label_zh=None,
                synonyms=[],
                turtle=axiom.turtle,
                subject_id=self._subject_id(axiom),
                flags=["non_standard"] if axiom.non_standard else [],
                required=False,
                multiple=False,
                auto_shape=False,
                status="active",
                origin=origin,
                revision=1,
                created_at=self._now,
                updated_at=self._now,
            )
            self._db.add(element)
            await self._db.flush()
            self._elements[element.id] = element
            item.applied_element_id = element.id
            return None
        resolution = self._plan.get(item.id)
        if resolution is not None and resolution.mode == "into" and resolution.item_id is None:
            return self._into(item, fields, resolved, resolution)
        if resolution is not None and resolution.mode == "into":
            joined = await self._joined(resolution.item_id)
            if joined is not None:
                self._add_to(joined, fields, resolved.get("parent_ref"), name_it=True)
                item.applied_element_id = joined.id
                return None
            # The item it was to go into was not applied: it is created on its own.
        renamed = resolution is not None and resolution.mode == "rename"
        local_name = resolution.local_name if resolution and renamed else fields.local_name
        if local_name is None or local_name in self._local_names:
            return INVALID_ITEM
        iri = fields.iri if fields.iri is not None else self._base_iri + local_name
        if iri in self._iris:
            return INVALID_ITEM
        member = kind in rules.RULE_PATH_KINDS
        auto_shape = fields.auto_shape if fields.auto_shape is not None else fields.iri is None
        element = Element(
            id=uuid4(),
            ontology_id=self._change_set.ontology_id,
            kind=kind,
            local_name=local_name,
            iri=fields.iri,
            label_zh=rules.clean_text(fields.label_zh),
            label_en=rules.clean_text(fields.label_en),
            definition_zh=rules.clean_text(fields.definition_zh),
            definition_en=rules.clean_text(fields.definition_en),
            synonyms=rules.merge_synonyms(fields.synonyms or []),
            parent_id=resolved.get("parent_ref"),
            domain_id=resolved.get("domain_ref"),
            range_id=resolved.get("range_ref"),
            inverse_id=resolved.get("inverse_ref"),
            datatype=fields.datatype if kind == "property" else None,
            unit=rules.clean_text(fields.unit) if kind == "property" else None,
            required=bool(fields.required) and member,
            multiple=bool(fields.multiple) and member,
            auto_shape=bool(auto_shape) and kind != "constraint",
            rules=stored_rules if kind == "constraint" else None,
            flags=[],
            status="active",
            origin=origin,
            revision=1,
            created_at=self._now,
            updated_at=self._now,
        )
        self._db.add(element)
        await self._db.flush()
        self._elements[element.id] = element
        self._local_names.add(local_name)
        self._iris[iri] = element
        item.applied_element_id = element.id
        return None

    async def _joined(self, item_id: UUID | None) -> Element | None:
        """The element an accepted item of this change set made, applying it first: an object
        type, relation or property that another item of the change set goes into."""
        other = self._items.get(item_id) if item_id else None
        if other is None or other.decision != "accepted" or other.id in self._visiting:
            return None
        if await self.apply(other) is not None or other.applied_element_id is None:
            return None
        element = self._elements.get(other.applied_element_id)
        return element if element is not None and element.kind == other.kind else None

    def _into(
        self,
        item: ChangeItem,
        fields: schemas.ElementFields,
        resolved: dict[str, UUID | None],
        resolution: mergeplan.Resolution,
    ) -> str | None:
        """Instead of creating a second element for the same thing, add to the first.

        Items that refer to this one end up referring to that element, through
        `applied_element_id`.
        """
        target = self._elements.get(resolution.element_id) if resolution.element_id else None
        if target is None or target.kind != item.kind or target.status != "active":
            return INVALID_ITEM
        self._add_to(target, fields, resolved.get("parent_ref"), name_it=True)
        item.applied_element_id = target.id
        return None

    def _append(self, item: ChangeItem, resolution: mergeplan.Resolution) -> str | None:
        """An update that only adds: applied whatever the target's revision is by now."""
        target = self._elements.get(resolution.element_id) if resolution.element_id else None
        if target is None or target.kind != item.kind or target.status != "active":
            return INVALID_ITEM
        fields = rules.effective_fields(item.proposed, item.edited)
        if rules.field_problems(
            item.kind,
            "update",
            fields,
            target_local_name=target.local_name,
            target_imported=target.iri is not None,
        ):
            return INVALID_ITEM
        self._add_to(target, fields, None, name_it=False)
        item.applied_element_id = target.id
        return None

    def _add_to(
        self,
        target: Element,
        fields: schemas.ElementFields,
        parent_id: UUID | None,
        *,
        name_it: bool,
    ) -> None:
        """Add what `fields` knows and `target` lacks. Nothing the element has is replaced.

        `name_it`: the fields describe an element of their own, whose label is one more name
        of the target when it is none of its names yet.
        """
        labels = {mergeplan.name_key(text) for text in (target.label_zh, target.label_en) if text}
        known = labels | {mergeplan.name_key(entry["text"]) for entry in target.synonyms}
        added: list[dict[str, Any]] = []
        label = rules.clean_text(fields.label_zh)
        if name_it and label is not None and mergeplan.name_key(label) not in known:
            added.append({"lang": "zh", "text": label})
        added += [
            {"lang": synonym.lang, "text": synonym.text}
            for synonym in fields.synonyms or []
            # Compared as names are compared everywhere: 高 炉 is the 高炉 it already has.
            if mergeplan.name_key(synonym.text) not in known
        ]
        # Compared in the merged form: tidying up the element's own list is no change.
        current = rules.merge_synonyms(target.synonyms)
        synonyms = rules.merge_synonyms(current, added)
        changed = synonyms != current
        if changed:
            target.synonyms = synonyms
        for column in ("definition_zh", "definition_en", "label_en", "unit"):
            if column == "label_en" and not name_it:
                continue
            if column == "unit" and target.kind != "property":
                continue
            value = rules.clean_text(getattr(fields, column))
            if value is not None and not getattr(target, column):
                setattr(target, column, value)
                changed = True
        if (
            target.kind == "entity_type"
            and target.parent_id is None
            and parent_id is not None
            and not self._has_ancestor(parent_id, target.id)
        ):
            target.parent_id = parent_id
            changed = True
        if changed:
            target.revision += 1
            target.updated_at = self._now

    def _has_ancestor(self, start: UUID, ancestor: UUID) -> bool:
        current: UUID | None = start
        seen: set[UUID] = set()
        while current is not None and current not in seen:
            if current == ancestor:
                return True
            seen.add(current)
            element = self._elements.get(current)
            current = element.parent_id if element else None
        return False

    def _update(
        self,
        item: ChangeItem,
        target: Element,
        fields: schemas.ElementFields,
        resolved: dict[str, UUID | None],
        stored_rules: list[dict[str, Any]] | None,
        axiom: NormalizedAxiom | None,
    ) -> str | None:
        given = fields.model_fields_set
        if "parent_ref" in resolved:
            parent_id = resolved["parent_ref"]
            if parent_id is not None and self._has_ancestor(parent_id, target.id):
                return INVALID_ITEM
            target.parent_id = parent_id
        for name, column in (
            ("domain_ref", "domain_id"),
            ("range_ref", "range_id"),
            ("inverse_ref", "inverse_id"),
        ):
            if name in resolved:
                setattr(target, column, resolved[name])
        if "label_zh" in given:
            target.label_zh = rules.clean_text(fields.label_zh)
        if "label_en" in given:
            target.label_en = rules.clean_text(fields.label_en)
        if "definition_zh" in given:
            target.definition_zh = rules.clean_text(fields.definition_zh)
        if "definition_en" in given:
            target.definition_en = rules.clean_text(fields.definition_en)
        if fields.synonyms is not None:
            if self._replace_synonyms:
                target.synonyms = rules.merge_synonyms(fields.synonyms)
            else:
                target.synonyms = rules.merge_synonyms(target.synonyms, fields.synonyms)
        if item.kind == "property":
            if "datatype" in given:
                target.datatype = fields.datatype
            if "unit" in given:
                target.unit = rules.clean_text(fields.unit)
        if item.kind in rules.RULE_PATH_KINDS:
            if fields.required is not None:
                target.required = fields.required
            if fields.multiple is not None:
                target.multiple = fields.multiple
        if fields.auto_shape is not None and item.kind != "constraint":
            target.auto_shape = fields.auto_shape
        if stored_rules is not None and item.kind == "constraint":
            target.rules = stored_rules
        if axiom is not None:
            target.turtle = axiom.turtle
            target.flags = ["non_standard"] if axiom.non_standard else []
            target.subject_id = self._subject_id(axiom)
        if item.op == "restore":
            target.status = "active"
        target.revision += 1
        target.updated_at = self._now
        item.applied_element_id = target.id
        return None

    def _used_by_others(self, target: Element, leaving: set[UUID]) -> bool:
        """Whether an element that stays active refers to `target`."""
        for element in self._elements.values():
            if element.status != "active" or element.id in leaving:
                continue
            columns = (element.parent_id, element.domain_id, element.range_id, element.inverse_id)
            if target.id in columns or element.subject_id == target.id:
                return True
            if target.id in _rule_references(element):
                return True
        return False

    def apply_deletes(self, items: Sequence[ChangeItem]) -> None:
        """Delete together what is only used by other elements deleted in this change set.

        A delete whose target an element outside the deleted set still uses is skipped with
        `changeset.has_dependents`; dropping it can make others fail too, so this repeats until
        the deleted set is closed. Two relations that are each other's inverse go together.
        """
        leaving: dict[UUID, tuple[ChangeItem, Element]] = {}
        for item in items:
            problem, target = self._target(item)
            fields = rules.effective_fields(item.proposed, item.edited)
            if problem is None and rules.field_problems(item.kind, "delete", fields):
                problem = INVALID_ITEM
            if problem is not None or target is None:
                self.outcomes[item.id] = problem
                continue
            leaving[item.id] = (item, target)
        changed = True
        while changed:
            changed = False
            ids = {target.id for _, target in leaving.values()}
            for item_id, (_, target) in list(leaving.items()):
                if self._used_by_others(target, ids):
                    self.outcomes[item_id] = HAS_DEPENDENTS
                    del leaving[item_id]
                    changed = True
        for item, target in leaving.values():
            target.status = "deprecated"
            target.revision += 1
            target.updated_at = self._now
            item.applied_element_id = target.id
            self.outcomes[item.id] = None


async def merge_change_set(
    db: AsyncSession,
    change_set_id: UUID,
    *,
    actor: UUID,
    ip: str | None,
    review_mode: ReviewMode,
    resolution_token: str | None = None,
) -> schemas.MergeResult:
    """Apply the accepted items to the working version in one transaction.

    Items of an AI-extracted change set are applied as planned against the working version
    (`mergeplan`): into an element that is the same thing, under another local name, or as
    additions. `resolution_token` is the token of the plan the reviewer saw; if the plan is
    another one by now, nothing is applied (409 `changeset.resolution_changed`).

    The order (spec 003, 6.3): creates, updates and restores of semantic elements (axioms after
    the others, so that an axiom finds the element it is about); binding deletes; binding
    creates, updates and restores, type bindings first; semantic deletes last. Skipped items:
    `changeset.stale_target` when the target changed after the item was proposed,
    `changeset.dependency_skipped` when a reference resolves to a rejected or skipped item (also
    transitively), `changeset.has_dependents` when a deleted element is still in use,
    `changeset.invalid_item` when the fields do not form a valid element, a reference is
    unusable, or the type hierarchy would become circular.
    """
    change_set = await _change_set_or_404(db, change_set_id)
    ontology = await _ontology_or_404(db, change_set.ontology_id, lock=True)
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
    _ensure_not_own(change_set, actor, review_mode)
    result = await _apply_change_set(
        db, change_set, ontology, actor=actor, ip=ip, resolution_token=resolution_token
    )
    await db.commit()
    return result


async def _apply_change_set(
    db: AsyncSession,
    change_set: ChangeSet,
    ontology: Ontology,
    *,
    actor: UUID,
    ip: str | None,
    resolution_token: str | None = None,
) -> schemas.MergeResult:
    """The merge without the commit: the caller holds the ontology and change set locks and
    decides whether to commit (a manual edit rolls back when any item was skipped)."""
    items = await _items(db, change_set)
    if any(item.decision == "pending" for item in items):
        raise AppError(409, "changeset.pending_items", "Every item needs a decision first.")
    now = _now()
    elements = await _elements(db, ontology.id, all_kinds=True)
    # Under the ontology lock: the plan made here is the one that is applied.
    plan = _plan(change_set, ontology, elements, items, await _links(db, change_set, items))
    seen = resolution_token == plan.token
    if not seen and (resolution_token is not None or plan.needs_token):
        raise AppError(
            409,
            RESOLUTION_CHANGED,
            "The working version changed since the change set was shown; review it again.",
        )
    merge = _Merge(db, change_set, ontology, elements, items, now, plan.resolutions)
    accepted = [item for item in items if item.decision == "accepted"]
    # Unsupported items must also be skipped when reached through another item's reference.
    merge.outcomes.update((item.id, INVALID_ITEM) for item in accepted if item.kind == "metric")
    semantic = [item for item in accepted if item.kind in SEMANTIC_KINDS]
    bound = [item for item in accepted if item.kind in BINDING_KINDS]
    ordered = [
        *(item for item in semantic if item.op != "delete" and item.kind != "axiom"),
        *(item for item in semantic if item.op != "delete" and item.kind == "axiom"),
    ]
    for item in ordered:
        await merge.apply(item)
    # Bindings leave before new ones come (spec 003, 6.3): a change set that replaces a type
    # binding would otherwise create the new one next to the old and skip it as a duplicate.
    merge.apply_deletes([item for item in bound if item.op == "delete"])
    await db.flush()
    # Type bindings first: a column or relation binding is checked against the key columns of
    # its type bindings as this change set leaves them, also when it names them by id.
    changing = [item for item in bound if item.op != "delete"]
    for item in sorted(changing, key=lambda item: BINDING_KINDS.index(item.kind)):
        await merge.apply(item)
    # Semantic elements leave last, after the bindings that referred to them.
    merge.apply_deletes([item for item in semantic if item.op == "delete"])
    skipped = [
        schemas.MergeSkip.model_validate({"item_id": item.id, "code": merge.outcomes[item.id]})
        for item in accepted
        if merge.outcomes[item.id] is not None
    ]
    applied = len(accepted) - len(skipped)
    change_set.status = "merged"
    change_set.merged_by = actor
    change_set.merged_at = now
    ontology.updated_at = now
    audit.record(
        db,
        "changeset.merged",
        actor_id=actor,
        target_type="change_set",
        target_id=str(change_set.id),
        detail={"ontologyId": str(ontology.id), "applied": applied, "skipped": len(skipped)},
        ip=ip,
    )
    return schemas.MergeResult(applied=applied, skipped=skipped)
