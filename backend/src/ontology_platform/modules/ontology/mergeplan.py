"""What merging an AI-extracted change set will do with each item (spec 004, section 5).

Documents uploaded together are identified against the same baseline, so their change sets
propose the same concepts independently. By the time the second one is merged, the working
version already holds what the first one created. The plan says, per item, whether it is
created as proposed, goes into an element that is the same thing, or gets another local name.

The plan is a pure function of plain data: the review page shows it before the merge, the merge
executes it, and the evaluation applies it without a database. No model is involved.
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from ontology_platform.modules.ontology import rules
from ontology_platform.modules.ontology.schemas import ElementFields

Mode = Literal["create", "into", "rename", "update"]

PLANNED_KINDS = ("entity_type", "relation_type", "property")
# What an AI update adds to its target without replacing anything; see `_additive`.
ADDITIVE_FIELDS = frozenset({"synonyms", "definition_zh"})
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class PlanElement:
    """An element of the working version, deleted ones included."""

    id: UUID
    kind: str
    status: str
    local_name: str | None
    iri: str | None
    label_zh: str | None
    label_en: str | None
    definition_zh: str | None
    definition_en: str | None
    parent_id: UUID | None
    domain_id: UUID | None
    range_id: UUID | None
    datatype: str | None
    unit: str | None
    required: bool
    multiple: bool
    revision: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PlanMatch:
    """The alignment record of an item (spec 004, 4.3): what it was found to be the same as.

    The other side is an element, or a create item: of this change set, or of another one, in
    which case the caller fills in the element that item was merged into (None while it is
    pending) and the decision its reviewer wrote on it.
    """

    kind: str  # same | possible
    element_id: UUID | None = None
    item_id: UUID | None = None
    item_element_id: UUID | None = None
    other_decision: str | None = None


@dataclass(frozen=True, slots=True)
class PlanMatchedBy:
    """A merged item of another change set whose record points at this item."""

    kind: str
    element_id: UUID  # what the other item was merged into
    decision: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PlanItem:
    """A change item with the fields a merge applies (the reviewer's edit over the proposal)."""

    id: UUID
    seq: int
    op: str
    kind: str
    decision: str
    temp_ref: str | None
    target_element_id: UUID | None
    target_revision: int | None
    fields: ElementFields
    edited: bool
    match: PlanMatch | None = None
    # The reviewer's conclusion about the item's alignment: same | different.
    match_decision: str | None = None
    matched_by: tuple[PlanMatchedBy, ...] = ()


@dataclass(frozen=True, slots=True)
class Resolution:
    mode: Mode
    # into, update: the element the item's content goes to, and its revision when planned.
    element_id: UUID | None = None
    element_revision: int | None = None
    # rename: the local name the new element gets.
    local_name: str | None = None
    # into, update: fields (wire names) the element already has a value for, which stays.
    kept_fields: tuple[str, ...] = ()
    # into: an item of this change set whose new element this one goes into (no element yet).
    item_id: UUID | None = None


def same_concept(kind: str, *decisions: str | None) -> bool:
    """The effective conclusion of an alignment record (spec 004, 5.3).

    Either side kept apart: not the same. Otherwise either side merged: the same. Without a
    decision, the record itself: "same" is, "possible" is not.
    """
    if "different" in decisions:
        return False
    return "same" in decisions or kind == "same"


def name_key(text: str) -> str:
    """Comparison key of a name: NFKC, lowercase, no whitespace (as the extraction's)."""
    return _WHITESPACE.sub("", unicodedata.normalize("NFKC", text)).lower()


def same_name(fields: ElementFields, element: PlanElement) -> bool:
    """Whether the proposed element and the existing one have the same main name.

    The Chinese labels decide. When either side has none, the English ones do; an element
    without any label goes by its local name, as everywhere the platform shows it.
    """
    proposed_zh = name_key(fields.label_zh or "")
    existing_zh = name_key(element.label_zh or "")
    if proposed_zh and existing_zh:
        return proposed_zh == existing_zh
    proposed_en = name_key(fields.label_en or "")
    existing_en = name_key(element.label_en or ("" if existing_zh else element.local_name or ""))
    return bool(proposed_en) and proposed_en == existing_en


def _additive(item: PlanItem) -> bool:
    """An update that only adds synonyms or a definition, as the extraction proposes them.

    It does not depend on what the target's other fields were when it was proposed, so a
    target that moved on does not make it stale. An item the reviewer edited is theirs: it
    keeps the optimistic lock, and replaces what it says it replaces.
    """
    given = item.fields.model_fields_set
    if item.edited or not given <= ADDITIVE_FIELDS:
        return False
    # A restore may carry nothing: bringing the element back is all it asks for.
    return bool(given) or item.op == "restore"


def _differs(proposed: str | None, existing: str | None) -> bool:
    """Whether the element keeps a value that the item would have set otherwise."""
    wanted, kept = rules.clean_text(proposed), rules.clean_text(existing)
    return wanted is not None and kept is not None and wanted != kept


def plan_merge(
    items: Sequence[PlanItem],
    elements: Sequence[PlanElement],
    *,
    base_iri: str,
) -> dict[UUID, Resolution]:
    """The resolution of every item whose outcome depends on the working version.

    Items missing from the result are applied as before: rejected items, deletes, restores of
    elements that are still deleted, updates the reviewer edited or that replace values, and
    kinds the extraction does not propose.
    """
    by_id = {element.id: element for element in elements}
    # The oldest first: of several elements that are the same thing, the first one stays.
    active = sorted(
        (element for element in elements if element.status == "active"),
        key=lambda element: (element.created_at, str(element.id)),
    )
    live = sorted((item for item in items if item.decision != "rejected"), key=lambda i: i.seq)
    creates = [item for item in live if item.op == "create" and item.kind in PLANNED_KINDS]
    by_ref = {item.temp_ref: item for item in creates if item.temp_ref is not None}
    plan: dict[UUID, Resolution] = {}

    def into(item: PlanItem, target: PlanElement) -> None:
        plan[item.id] = Resolution("into", element_id=target.id, element_revision=target.revision)

    def endpoint(ref: str | None) -> UUID | None:
        """The existing element a reference will point at; None for a new or unknown one."""
        if ref is None:
            return None
        element_id = rules.parse_id(ref)
        if element_id is not None:
            return element_id if element_id in by_id else None
        resolution = plan.get(by_ref[ref].id) if ref in by_ref else None
        return resolution.element_id if resolution and resolution.mode == "into" else None

    def active_type(element_id: UUID | None) -> PlanElement | None:
        element = by_id.get(element_id) if element_id else None
        ok = element is not None and element.kind == "entity_type" and element.status == "active"
        return element if ok else None

    by_item = {item.id: item for item in creates}
    # Object types first: relations and properties are the same as existing ones only once
    # their ends are known. An object type is an active one of the same main name, or what its
    # alignment record says it is (spec 004, 5.3).
    for item in creates:
        if item.kind != "entity_type":
            continue
        target = next(
            (e for e in active if e.kind == "entity_type" and same_name(item.fields, e)), None
        )
        record = item.match
        if (
            target is None
            and record is not None
            and same_concept(record.kind, item.match_decision, record.other_decision)
        ):
            target = active_type(record.element_id) or active_type(record.item_element_id)
            other = by_item.get(record.item_id) if record.item_id else None
            if target is None and other is not None and other.seq < item.seq:
                found = plan.get(other.id)
                if found is not None and found.mode == "into":
                    plan[item.id] = found
                else:
                    plan[item.id] = Resolution("into", item_id=other.id)
                continue
        if target is None:
            reverse = sorted(
                (
                    entry
                    for entry in item.matched_by
                    if same_concept(entry.kind, entry.decision, item.match_decision)
                    and active_type(entry.element_id) is not None
                ),
                key=lambda entry: entry.created_at,
            )
            target = active_type(reverse[0].element_id) if reverse else None
        if target is not None:
            into(item, target)
    for item in creates:
        if item.kind == "entity_type":
            continue
        domain = endpoint(item.fields.domain_ref)
        if domain is None:
            continue
        range_ = endpoint(item.fields.range_ref) if item.kind == "relation_type" else None
        if item.kind == "relation_type" and range_ is None:
            continue
        target = next(
            (
                e
                for e in active
                if e.kind == item.kind
                and e.domain_id == domain
                and e.range_id == range_
                and same_name(item.fields, e)
            ),
            None,
        )
        if target is not None:
            into(item, target)

    # Local names: an item keeps the one it asks for when it is free. Every creation reserves
    # its name before any other is chosen, so that a renamed item never takes a name a later
    # item asked for, planned or not (constraints, items with an IRI of their own).
    taken_names = {element.local_name for element in elements if element.local_name}
    taken_iris = {element.iri for element in elements if element.iri}
    renamed: list[tuple[PlanItem, str]] = []
    planned = {item.id for item in creates}
    for item in live:
        wanted = item.fields.local_name
        if item.op != "create" or item.id in plan or wanted is None:
            continue
        iri = item.fields.iri or base_iri + wanted
        # Only what the extraction proposes is renamed; an explicit IRI is the item's identity.
        clash = wanted in taken_names or iri in taken_iris
        if clash and item.id in planned and item.fields.iri is None:
            renamed.append((item, wanted))
        else:
            taken_names.add(wanted)
            taken_iris.add(iri)
    for item, wanted in renamed:
        name, counter = f"{wanted}2", 3
        while name in taken_names or base_iri + name in taken_iris:
            name, counter = f"{wanted}{counter}", counter + 1
        if len(name) > rules.LOCAL_NAME_MAX_LENGTH:
            continue  # no name left to give it: it stays an invalid item, as before
        taken_names.add(name)
        plan[item.id] = Resolution("rename", local_name=name)
    for item in creates:
        plan.setdefault(item.id, Resolution("create"))

    for item in creates:
        resolution = plan[item.id]
        if resolution.mode != "into" or resolution.element_id is None:
            continue
        kept = _kept_by(by_id[resolution.element_id], item.fields, endpoint, by_id)
        plan[item.id] = Resolution(
            "into",
            element_id=resolution.element_id,
            element_revision=resolution.element_revision,
            kept_fields=kept,
        )

    for item in live:
        # A restore whose target is active again (another change set restored it) has only
        # its additions left to apply.
        if item.op not in ("update", "restore") or not _additive(item):
            continue
        target = by_id.get(item.target_element_id) if item.target_element_id else None
        if target is None or target.kind != item.kind or target.status != "active":
            continue
        kept = (
            ("definitionZh",) if _differs(item.fields.definition_zh, target.definition_zh) else ()
        )
        plan[item.id] = Resolution(
            "update", element_id=target.id, element_revision=target.revision, kept_fields=kept
        )
    return plan


def _kept_by(
    target: PlanElement,
    fields: ElementFields,
    endpoint: Callable[[str | None], UUID | None],
    by_id: Mapping[UUID, PlanElement],
) -> tuple[str, ...]:
    """Fields of an item going into `target` that differ from what the element has and keeps."""
    kept: list[str] = []
    if _differs(fields.label_en, target.label_en):
        kept.append("labelEn")
    if _differs(fields.definition_zh, target.definition_zh):
        kept.append("definitionZh")
    if _differs(fields.definition_en, target.definition_en):
        kept.append("definitionEn")
    if target.kind == "entity_type":
        parent = fields.parent_ref
        parent_id = endpoint(parent)
        has_other_parent = target.parent_id is not None and parent_id != target.parent_id
        # The merge leaves out a parent that would make the hierarchy circular.
        circular = target.parent_id is None and _below(parent_id, target.id, by_id)
        if parent is not None and (has_other_parent or circular):
            kept.append("parentRef")
        return tuple(kept)
    if target.kind == "property":
        if fields.datatype is not None and fields.datatype != target.datatype:
            kept.append("datatype")
        if _differs(fields.unit, target.unit):
            kept.append("unit")
    if fields.required is not None and fields.required != target.required:
        kept.append("required")
    if fields.multiple is not None and fields.multiple != target.multiple:
        kept.append("multiple")
    return tuple(kept)


def _below(start: UUID | None, ancestor: UUID, by_id: Mapping[UUID, PlanElement]) -> bool:
    """Whether `start` is `ancestor` or lies under it in the type hierarchy."""
    seen: set[UUID] = set()
    current = start
    while current is not None and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        element = by_id.get(current)
        current = element.parent_id if element else None
    return False


def plan_token(
    items: Sequence[PlanItem],
    elements: Sequence[PlanElement],
    plan: Mapping[UUID, Resolution],
) -> str:
    """A digest of everything in the plan that depends on the current working version.

    A reviewer merges with the token of the plan they were shown. It changes when an item
    would go elsewhere, get another name, or when the element it goes to has changed since.
    """
    by_id = {element.id: element for element in elements}
    entries: list[list[str | int | None]] = []
    for item in sorted(items, key=lambda item: str(item.id)):
        if item.decision == "rejected":
            continue
        resolution = plan.get(item.id)
        if resolution is not None and resolution.mode != "create":
            target_id = resolution.element_id or resolution.item_id
            target = str(target_id) if target_id else None
            entries.append(
                [
                    str(item.id),
                    resolution.mode,
                    target,
                    resolution.element_revision,
                    resolution.local_name,
                ]
            )
        elif resolution is None and item.op == "restore" and item.target_element_id in by_id:
            restored = by_id[item.target_element_id]
            entries.append([str(item.id), "restore", str(restored.id), restored.revision, None])
    text = json.dumps(entries, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def changes_the_merge(items: Sequence[PlanItem], plan: Mapping[UUID, Resolution]) -> bool:
    """Whether the plan does anything a merge did not do before there were plans.

    Such a merge needs the reviewer's token. Without one, only a merge that behaves exactly as
    it used to is allowed, so that callers that predate the token keep working.
    """
    for item in items:
        resolution = plan.get(item.id)
        if resolution is None or resolution.mode == "create":
            continue
        if resolution.mode in ("into", "rename") or item.op == "restore":
            return True
        if resolution.element_revision != item.target_revision:
            return True
    return False
