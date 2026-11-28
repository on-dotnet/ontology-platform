"""Extraction quality on a case pack: `python -m ontology_platform.modules.ai.eval`.

Reads a JSON bundle on stdin:
  {"files": {"docs/<name>": "<base64>", "eval/expected.toml": "<base64>"},
   "recordings": ["<text of a recording file>", ...], "manifest": "<models.json text>" | null,
   "mode": "record" | "replay", "scenarios": ["sequential", "sameBaseline"]}
Runs the model over every document in order and merges each change set with every item
accepted, through the merge plan of the ontology module (spec 004, 5.2), so that later
documents align with what earlier ones produced (the sequential scenario). The same-baseline
scenario, unless `scenarios` leaves it out, identifies every document against the starting
ontology and merges the change sets in order afterwards. Each scenario scores entity types,
relations and, when eval/expected.toml has them, properties and hierarchy (format in
docs/development.md), and counts what merging skipped and duplicated. A case without
eval/expected.toml (private documents whose answers come later) is run and not scored.

Model calls go through `ReplayGateway`: a call whose input was recorded is answered from the
recording. "record" calls the model for the others and returns their recordings; "replay"
fails on the first call that was not recorded and needs no model key. "replay" uses the models
of the last recorded run (models.json), so that a workspace without the model settings asks
for the same keys. Ids of documents, chunks and accepted elements follow from names, since the
ids of existing types are part of later prompts.

Progress goes to stderr. Stdout is JSON Lines: a models.json file line before the first
recording file line, then one file line per new recording, flushed immediately. The last
line is a result or error object. Interrupted runs retain the file lines already emitted.

The result keeps the merged elements and parents, so that a changed expected.toml can be
scored against the same run: `--rescore` reads {"expected": "<toml text>", "elements": [...],
"parents": {...}} on stdin and prints the score.
"""

import asyncio
import base64
import json
import sys
import time
import tomllib
import traceback
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid5

from pydantic import BaseModel

from ontology_platform.modules.ai.candidates import THRESHOLD, Names, group_recall
from ontology_platform.modules.ai.candidates import score as candidate_score
from ontology_platform.modules.ai.extraction import (
    TYPES_BATCH_TERMS,
    ChunkText,
    ExtractionModels,
    Extractor,
    JudgedPair,
    KnownElement,
    MemoryOutcome,
    PendingType,
    Proposal,
    ProposedMatch,
    RunStats,
    _aliases,
    _as_uuid,
    _unalias,
    merge_types,
    normalize,
    relations_catalog,
    types_context,
)
from ontology_platform.modules.ai.gateway import AiError, InputFile, ModelGateway
from ontology_platform.modules.ai.pipeline import to_item
from ontology_platform.modules.ai.prompts import EntityTypeOut, TermsOut, TypesOut
from ontology_platform.modules.ai.replay import (
    STAGE_COUNTS,
    MeteredGateway,
    RecordingStream,
    ReplayGateway,
    ReplayMissError,
    load_recordings,
    write_json_line,
)
from ontology_platform.modules.documents.chunking import chunk_pages
from ontology_platform.modules.documents.parsers import detect_type, parse_document
from ontology_platform.modules.ontology.review_memory import (
    DecidedItem,
    ReviewMemory,
    apply_delta,
    collect,
    pair_key,
    property_key,
    relation_key,
    type_key,
)
from ontology_platform.modules.ontology.schemas import ElementFields
from ontology_platform.modules.ontology.service import (
    PlanElement,
    PlanItem,
    RecordedItem,
    Resolution,
    link_records,
    plan_merge,
)
from ontology_platform.settings import Settings

_NAMESPACE = UUID("6f1d3c52-8a4e-4d0b-9f57-2c1e0b7a9d43")
MANIFEST = "models.json"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def stable_id(*parts: str) -> UUID:
    return uuid5(_NAMESPACE, "/".join(parts))


INVALID_ITEM = "changeset.invalid_item"
DEPENDENCY_SKIPPED = "changeset.dependency_skipped"
STALE_TARGET = "changeset.stale_target"
BASE_IRI = "https://eval.invalid/"
_REF_KIND = "entity_type"  # what parentRef, domainRef and rangeRef point at
_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


class WorkingVersion:
    """The ontology of a run, which change sets are merged into as a reviewer accepting
    everything would merge them: through the merge plan (spec 004, 5.2), so that an item goes
    into the element that is the same thing, or gets another local name, as at a real merge.

    `elements` are the active elements in the order they were created; `parents` the object
    types' parents. New elements get ids derived from their local names (unique within a run),
    so that a rerun shows the model the same ids. There are no deletes: nothing is restored.
    """

    def __init__(self) -> None:
        self.elements: list[KnownElement] = []
        self.parents: dict[UUID, UUID] = {}
        # Flags of the item that created an element: whether a duplicate was marked ("aligned":
        # the item carried an alignment record).
        self.flags: dict[UUID, tuple[str, ...]] = {}
        # Merged items as alignment records see them (spec 004, 5.3): what each became, the
        # decision its reviewer wrote, and its own record.
        self.recorded: dict[UUID, RecordedItem] = {}
        self._merges = 0
        self.same_kept_apart = 0

    def copy(self) -> "WorkingVersion":
        other = WorkingVersion()
        other.elements, other.parents, other.flags = (
            list(self.elements),
            dict(self.parents),
            dict(self.flags),
        )
        other.recorded = dict(self.recorded)
        other._merges = self._merges
        other.same_kept_apart = self.same_kept_apart
        return other

    def known(self) -> list[KnownElement]:
        """The elements as an extraction sees them, object types with their parents."""
        return [replace(e, parent_id=self.parents.get(e.id)) for e in self.elements]

    def merge(
        self,
        proposals: Sequence[Proposal],
        label: str | None = None,
        decide: "Callable[[Proposal, ProposedMatch], str | None] | None" = None,
    ) -> list[str]:
        """Merges one change set with every item accepted; returns the codes of skipped items.

        `label` names the change set, so that items of later ones can refer to its items (as
        pending ones); `decide` is the reviewer's decision on an item's alignment record.
        """
        self._merges += 1
        label = label if label is not None else f"#{self._merges}"
        ids = [item_id(label, seq) for seq in range(1, len(proposals) + 1)]
        by_ref = {
            proposal.temp_ref: ids[index]
            for index, proposal in enumerate(proposals)
            if proposal.op == "create" and proposal.temp_ref
        }
        change_set = stable_id("changeset", label)
        decisions: list[str | None] = []
        recorded: list[RecordedItem] = []
        for seq, proposal in enumerate(proposals, start=1):
            record = proposal.match
            decision = decide(proposal, record) if decide is not None and record else None
            if record is not None and record.kind == "same" and decision == "different":
                self.same_kept_apart += 1
            decisions.append(decision)
            other = None
            if record is not None:
                other = record.item_id or (by_ref.get(record.temp_ref) if record.temp_ref else None)
            recorded.append(
                RecordedItem(
                    id=ids[seq - 1],
                    change_set_id=change_set,
                    match_kind=record.kind if record else None,
                    match_element_id=record.element_id if record else None,
                    match_item_id=other,
                    match_decision=decision,
                    label_zh=proposal.fields.get("labelZh"),
                    label_en=proposal.fields.get("labelEn"),
                )
            )
        # The same resolution of records as the merge's (`ontology.service`), on plain data.
        here = {item.id: item for item in recorded}
        wanted = {item.match_item_id for item in recorded if item.match_item_id}
        matches, matched_by = link_records(
            recorded,
            {
                key: here.get(key) or self.recorded[key]
                for key in wanted
                if key in here or key in self.recorded
            },
            [item for item in self.recorded.values() if item.match_item_id in here],
        )
        items: list[PlanItem] = []
        for seq, proposal in enumerate(proposals, start=1):
            own = ids[seq - 1]
            match = matches.get(own)
            decision = decisions[seq - 1]
            items.append(
                PlanItem(
                    id=own,
                    seq=seq,
                    op=proposal.op,
                    kind=proposal.kind,
                    decision="accepted",
                    temp_ref=proposal.temp_ref,
                    target_element_id=proposal.target_element_id,
                    target_revision=proposal.target_revision,
                    fields=to_item(proposal, _EVAL_DOCUMENT).proposed,
                    edited=False,
                    match=match,
                    match_decision=decision,
                    matched_by=matched_by.get(own, ()),
                )
            )
        plan = plan_merge(items, self._plan_elements(), base_iri=BASE_IRI)
        proposal_of = {item.id: proposal for item, proposal in zip(items, proposals, strict=True)}
        creates = {item.temp_ref: item for item in items if item.op == "create" and item.temp_ref}
        by_item = {item.id: item for item in items}
        outcomes: dict[UUID, str | None] = {}
        made: dict[UUID, UUID] = {}  # item -> the element it created or went into
        visiting: set[UUID] = set()
        start = len(self.elements)

        def apply(item: PlanItem) -> str | None:
            if item.id in outcomes:
                return outcomes[item.id]
            visiting.add(item.id)
            try:
                outcome, element_id = self._apply(
                    item, proposal_of[item.id], plan.get(item.id), resolve, joined
                )
            finally:
                visiting.discard(item.id)
            outcomes[item.id] = outcome
            if element_id is not None:
                made[item.id] = element_id
            return outcome

        def resolve(ref: str) -> tuple[str | None, UUID | None]:
            # As the merge does: an item made in the same change set is applied first, wherever
            # it stands (the model may list a subtype before its parent).
            dependency = creates.get(ref)
            if dependency is None:
                element_id = _uuid(ref)
                element = next((e for e in self.elements if e.id == element_id), None)
                if element is None or element.kind != _REF_KIND:
                    return INVALID_ITEM, None
                return None, element.id
            if dependency.kind != _REF_KIND or dependency.id in visiting:
                return INVALID_ITEM, None
            if apply(dependency) is not None:
                return DEPENDENCY_SKIPPED, None
            return None, made[dependency.id]

        def joined(target: UUID) -> UUID | None:
            """The element an item of this change set made, applying it first; None if not."""
            dependency = by_item[target]
            if dependency.id in visiting or apply(dependency) is not None:
                return None
            return made.get(dependency.id)

        for item in items:
            apply(item)
        # New elements keep the order of their items, whatever order dependencies made them in.
        seq_of = {
            element_id: item.seq for item in reversed(items) if (element_id := made.get(item.id))
        }
        self.elements[start:] = sorted(self.elements[start:], key=lambda e: seq_of[e.id])
        merged_at = _EPOCH + timedelta(seconds=self._merges)
        for entry in recorded:
            self.recorded[entry.id] = replace(
                entry, merged_into=made.get(entry.id), merged_at=merged_at
            )
        return [code for item in items if (code := outcomes[item.id]) is not None]

    def _plan_elements(self) -> list[PlanElement]:
        return [
            PlanElement(
                id=element.id,
                kind=element.kind,
                status="active",
                local_name=element.local_name,
                iri=BASE_IRI + element.local_name,
                label_zh=element.label_zh,
                label_en=element.label_en,
                definition_zh=element.definition_zh,
                definition_en=None,
                parent_id=self.parents.get(element.id),
                domain_id=element.domain_id,
                range_id=element.range_id,
                datatype=None,
                unit=None,
                required=False,
                multiple=False,
                revision=element.revision,
                created_at=_EPOCH + timedelta(microseconds=index),
            )
            for index, element in enumerate(self.elements)
        ]

    def _apply(
        self,
        item: PlanItem,
        proposal: Proposal,
        resolution: Resolution | None,
        resolve: Callable[[str], tuple[str | None, UUID | None]],
        joined: Callable[[UUID], UUID | None],
    ) -> tuple[str | None, UUID | None]:
        """The code the item is skipped with (or None) and the element it went into."""
        by_id = {element.id: element for element in self.elements}
        if item.op != "create":
            target = by_id.get(item.target_element_id) if item.target_element_id else None
            if target is None or target.kind != item.kind or item.op == "restore":
                return INVALID_ITEM, None  # nothing is deleted in a run, so nothing to restore
            if resolution is None and target.revision != item.target_revision:
                return STALE_TARGET, None
            self._add_to(target, item.fields, None, name_it=False)
            return None, target.id
        refs: dict[str, UUID | None] = {}
        for name in ("parent_ref", "domain_ref", "range_ref"):
            ref = getattr(item.fields, name)
            if ref is None:
                continue
            outcome, element_id = resolve(ref)
            if outcome is not None:
                return outcome, None
            refs[name] = element_id
        by_id = {element.id: element for element in self.elements}  # resolving may add some
        if resolution is not None and resolution.mode == "into" and resolution.item_id:
            joined_id = joined(resolution.item_id)
            if joined_id is not None:
                target = next(e for e in self.elements if e.id == joined_id)
                self._add_to(target, item.fields, refs.get("parent_ref"))
                return None, joined_id
            # The item it goes into was not applied: it is created on its own.
        if resolution is not None and resolution.mode == "into" and resolution.element_id:
            self._add_to(by_id[resolution.element_id], item.fields, refs.get("parent_ref"))
            return None, resolution.element_id
        local_name = (
            resolution.local_name
            if resolution is not None and resolution.mode == "rename" and resolution.local_name
            else item.fields.local_name or ""
        )
        if local_name in {element.local_name for element in self.elements}:
            return INVALID_ITEM, None
        element_id = self._new_id(item.kind, local_name)
        self.elements.append(
            KnownElement(
                id=element_id,
                kind=proposal.kind,
                local_name=local_name,
                label_zh=item.fields.label_zh or "",
                label_en=item.fields.label_en,
                synonyms=tuple(synonym.text for synonym in item.fields.synonyms or []),
                definition_zh=item.fields.definition_zh,
                domain_id=refs.get("domain_ref"),
                range_id=refs.get("range_ref"),
            )
        )
        if refs.get("parent_ref") is not None:
            self.parents[element_id] = cast(UUID, refs["parent_ref"])
        self.flags[element_id] = tuple(proposal.flags) + (("aligned",) if proposal.match else ())
        return None, element_id

    def _new_id(self, kind: str, local_name: str) -> UUID:
        used = {element.id for element in self.elements}
        element_id, counter = stable_id(kind, local_name), 2
        while element_id in used:
            element_id, counter = stable_id(kind, local_name, str(counter)), counter + 1
        return element_id

    def _add_to(
        self,
        target: KnownElement,
        fields: ElementFields,
        parent_id: UUID | None,
        *,
        name_it: bool = True,
    ) -> None:
        """Adds what `fields` knows and `target` lacks, as a merge does; nothing is replaced."""
        known = {normalize(name) for name in (target.label_zh, target.label_en or "") if name}
        known |= {normalize(name) for name in target.synonyms}
        added: list[str] = []
        if name_it and fields.label_zh and normalize(fields.label_zh) not in known:
            added.append(fields.label_zh)
            known.add(normalize(fields.label_zh))
        for synonym in fields.synonyms or []:
            if normalize(synonym.text) not in known:
                added.append(synonym.text)
                known.add(normalize(synonym.text))
        updated = replace(target, synonyms=target.synonyms + tuple(added))
        if fields.definition_zh and not target.definition_zh:
            updated = replace(updated, definition_zh=fields.definition_zh)
        if name_it and fields.label_en and not target.label_en:
            updated = replace(updated, label_en=fields.label_en)
        changed = updated != target
        if (
            target.kind == "entity_type"
            and target.id not in self.parents
            and parent_id is not None
            and not self._below(parent_id, target.id)
        ):
            self.parents[target.id] = parent_id
            changed = True
        if changed:
            updated = replace(updated, revision=target.revision + 1)
            self.elements = [updated if e.id == target.id else e for e in self.elements]

    def _below(self, start: UUID, ancestor: UUID) -> bool:
        seen: set[UUID] = set()
        current: UUID | None = start
        while current is not None and current not in seen:
            if current == ancestor:
                return True
            seen.add(current)
            current = self.parents.get(current)
        return False


_EVAL_DOCUMENT = UUID(int=0)


def item_id(label: str, seq: int) -> UUID:
    """The id of a change set's item in a run: later documents see it as a pending item."""
    return stable_id("item", label, str(seq))


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def merge_counts(
    version: WorkingVersion, skipped: Sequence[str], expected: Mapping[str, Any] | None
) -> dict[str, Any]:
    """What merging left behind (spec 004, section 10), for a reviewer who accepts everything.

    Duplicate types are groups of the expected list with several types: by main name (the
    same Chinese label), marked (a member was proposed as a possible duplicate or with an
    alignment record) or unmarked. A type joins a group by its main names only (Chinese and
    English label, local name): a generic synonym such as 缺陷 on 板坯表面缺陷 would put a
    distinct type into another type's group.
    Duplicate relations have the ends and the label of an earlier one.
    """
    codes = Counter(skipped)
    seen: set[tuple[UUID | None, UUID | None, str]] = set()
    duplicate_relations = 0
    for element in version.elements:
        if element.kind != "relation_type":
            continue
        key = (element.domain_id, element.range_id, normalize(element.label_zh))
        duplicate_relations += key in seen
        seen.add(key)
    counts: dict[str, Any] = {
        "review": "acceptAll",
        "skipped": len(skipped),
        "skippedByCode": dict(sorted(codes.items())),
        "duplicateRelations": duplicate_relations,
        # Items the model judged the same that the reviewer kept apart (by-flags review).
        "sameKeptApart": version.same_kept_apart,
    }
    if expected is None:
        return counts
    groups = [{normalize(n) for n in group["names"]} for group in expected["entity_types"]]
    members: dict[int, list[KnownElement]] = {}
    for element in version.elements:
        if element.kind != "entity_type":
            continue
        names = _main_names(element)
        group = next((i for i, g in enumerate(groups) if names & g), None)
        if group is not None:
            members.setdefault(group, []).append(element)
    duplicates = [found for found in members.values() if len(found) > 1]
    same_name = [
        found for found in duplicates if len({normalize(e.label_zh) for e in found}) < len(found)
    ]
    marked = [
        found
        for found in duplicates
        if found not in same_name
        and any(
            flag in ("possible_duplicate", "aligned")
            for e in found
            for flag in version.flags.get(e.id, ())
        )
    ]
    counts["duplicateTypeGroups"] = {
        "total": len(duplicates),
        "sameMainName": len(same_name),
        "marked": len(marked),
        "unmarked": len(duplicates) - len(same_name) - len(marked),
        "groups": sorted(" / ".join(e.label_zh for e in found) for found in duplicates),
    }
    return counts


def dump_elements(known: Sequence[KnownElement]) -> list[dict[str, Any]]:
    return [
        {
            key: (str(value) if isinstance(value, UUID) else value)
            for key, value in asdict(element).items()
        }
        for element in known
    ]


def load_elements(saved: Sequence[dict[str, Any]]) -> list[KnownElement]:
    def uuid_or_none(value: Any) -> UUID | None:
        return UUID(value) if value else None

    return [
        KnownElement(
            **{
                **item,
                "id": UUID(item["id"]),
                "synonyms": tuple(item["synonyms"]),
                "domain_id": uuid_or_none(item["domain_id"]),
                "range_id": uuid_or_none(item["range_id"]),
                "parent_id": uuid_or_none(item.get("parent_id")),
            }
        )
        for item in saved
    ]


def _main_names(element: KnownElement) -> set[str]:
    values = {element.label_zh, element.local_name, element.label_en}
    return {normalize(value) for value in values if value}


def _names(element: KnownElement) -> set[str]:
    return _main_names(element) | {normalize(value) for value in element.synonyms if value}


def _ratio(hits: int, total: int) -> float | None:
    """None when there is nothing to divide by (no predictions, or no core entries)."""
    return round(hits / total, 3) if total else None


class ExpectedError(ValueError):
    """eval/expected.toml is malformed; the message names the entry."""


def _names_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(n, str) for n in value)


def check_expected(expected: Mapping[str, Any]) -> None:
    """Fails on the first malformed entry: a missing field, or an end that names no type.

    Also on what `score` cannot divide by: types and relations need a core entry each.
    """
    types = expected.get("entity_types")
    if not types or not isinstance(types, list):
        raise ExpectedError("entity_types is missing or empty")
    first_names: set[str] = set()
    for index, entry in enumerate(types):
        if not _names_list(entry.get("names")) or not isinstance(entry.get("core"), bool):
            raise ExpectedError(f"entity_types[{index}] needs names (a list) and core")
        first_names.add(normalize(entry["names"][0]))
    for section in ("entity_types", "relations"):
        if not any(entry.get("core") is True for entry in expected.get(section, [])):
            raise ExpectedError(f"{section} needs at least one core entry")
    ends = {
        "relations": ("domain", "range"),
        "properties": ("domain",),
        "hierarchy": ("child", "parent"),
    }
    for section, fields in ends.items():
        for index, entry in enumerate(expected.get(section, [])):
            if not isinstance(entry.get("core"), bool):
                raise ExpectedError(f"{section}[{index}] needs core")
            if section == "properties" and not _names_list(entry.get("names")):
                raise ExpectedError(f"{section}[{index}] needs names (a list)")
            for field in fields:
                if normalize(str(entry.get(field, ""))) not in first_names:
                    raise ExpectedError(
                        f"{section}[{index}].{field} = {entry.get(field)!r} is not the first "
                        "name of an entity type"
                    )


def parse_expected(text: str) -> dict[str, Any]:
    try:
        expected = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ExpectedError(f"eval/expected.toml is not valid TOML: {exc}") from None
    check_expected(expected)
    return expected


def score(
    known: Sequence[KnownElement],
    expected: dict[str, Any],
    parents: Mapping[UUID, UUID] | None = None,
) -> dict[str, Any]:
    groups = [{normalize(n) for n in group["names"]} for group in expected["entity_types"]]
    first_name = {normalize(g["names"][0]): i for i, g in enumerate(expected["entity_types"])}
    types = [e for e in known if e.kind == "entity_type"]
    group_of: dict[UUID, int | None] = {}
    for element in types:
        names = _names(element)
        group_of[element.id] = next((i for i, g in enumerate(groups) if names & g), None)

    core_types = [i for i, g in enumerate(expected["entity_types"]) if g["core"]]
    found_groups = {g for g in group_of.values() if g is not None}
    type_precision = sum(g is not None for g in group_of.values()) / len(types) if types else 0.0
    type_recall = sum(i in found_groups for i in core_types) / len(core_types)

    expected_pairs = [
        (
            frozenset({first_name[normalize(r["domain"])], first_name[normalize(r["range"])]}),
            r["core"],
        )
        for r in expected["relations"]
    ]
    relations = [e for e in known if e.kind == "relation_type"]
    predicted_pairs = [
        frozenset(
            {
                group_of.get(r.domain_id) if r.domain_id else None,
                group_of.get(r.range_id) if r.range_id else None,
            }
        )
        for r in relations
    ]
    valid_pairs = {pair for pair, _ in expected_pairs}
    relation_precision = (
        sum(pair in valid_pairs for pair in predicted_pairs) / len(relations) if relations else 0.0
    )
    core_pairs = [pair for pair, core in expected_pairs if core]
    relation_recall = sum(pair in set(predicted_pairs) for pair in core_pairs) / len(core_pairs)
    label = {element.id: element.label_zh for element in types}
    unmatched_relations = sorted(
        f"{label.get(r.domain_id, '?') if r.domain_id else '?'} → "
        f"{label.get(r.range_id, '?') if r.range_id else '?'}（{r.label_zh}）"
        for r, pair in zip(relations, predicted_pairs, strict=True)
        if pair not in valid_pairs
    )

    properties = [e for e in known if e.kind == "property"]
    hierarchy = [(child, parent) for child, parent in (parents or {}).items() if child in label]
    result: dict[str, Any] = {
        "entityTypes": {
            "predicted": len(types),
            "precision": round(type_precision, 3),
            "recall": round(type_recall, 3),
            "unmatched": sorted(e.label_zh for e in types if group_of[e.id] is None),
            "missedCore": [
                expected["entity_types"][i]["names"][0] for i in core_types if i not in found_groups
            ],
        },
        "relations": {
            "predicted": len(relations),
            "precision": round(relation_precision, 3),
            "recall": round(relation_recall, 3),
            "unmatched": unmatched_relations,
        },
        "properties": {"predicted": len(properties)},
        "hierarchy": {"predicted": len(hierarchy)},
    }
    if "properties" in expected:
        result["properties"] = _score_properties(
            properties, expected["properties"], first_name, group_of, label
        )
    if "hierarchy" in expected:
        result["hierarchy"] = _score_hierarchy(
            hierarchy, expected["hierarchy"], first_name, group_of, label
        )
    return result


def _score_properties(
    properties: Sequence[KnownElement],
    entries: Sequence[dict[str, Any]],
    first_name: Mapping[str, int],
    group_of: Mapping[UUID, int | None],
    label: Mapping[UUID, str],
) -> dict[str, Any]:
    """A property matches an entry when it belongs to the entry's type and shares a name."""
    wanted = [
        (first_name[normalize(e["domain"])], {normalize(n) for n in e["names"]}) for e in entries
    ]
    found: set[int] = set()
    matched = 0
    unmatched: list[str] = []
    for prop in properties:
        group = group_of.get(prop.domain_id) if prop.domain_id else None
        names = _names(prop)
        hits = [
            i
            for i, (owner, wanted_names) in enumerate(wanted)
            if group is not None and owner == group and names & wanted_names
        ]
        if hits:
            matched += 1
            found.update(hits)
        else:
            owner_label = label.get(prop.domain_id, "?") if prop.domain_id else "?"
            unmatched.append(f"{owner_label}.{prop.label_zh}")
    core = [i for i, entry in enumerate(entries) if entry["core"]]
    return {
        "predicted": len(properties),
        "precision": _ratio(matched, len(properties)),
        "recall": _ratio(sum(i in found for i in core), len(core)),
        "unmatched": sorted(unmatched),
        "missedCore": [
            f"{entries[i]['domain']}.{entries[i]['names'][0]}" for i in core if i not in found
        ],
    }


def _score_hierarchy(
    pairs: Sequence[tuple[UUID, UUID]],
    entries: Sequence[dict[str, Any]],
    first_name: Mapping[str, int],
    group_of: Mapping[UUID, int | None],
    label: Mapping[UUID, str],
) -> dict[str, Any]:
    """Child → parent pairs of expected types; unlike relations, direction counts."""
    wanted = [
        (first_name[normalize(e["child"])], first_name[normalize(e["parent"])]) for e in entries
    ]
    predicted = [(group_of.get(child), group_of.get(parent)) for child, parent in pairs]
    valid = set(wanted)
    core = [i for i, entry in enumerate(entries) if entry["core"]]
    return {
        "predicted": len(pairs),
        "precision": _ratio(sum(pair in valid for pair in predicted), len(pairs)),
        "recall": _ratio(sum(wanted[i] in set(predicted) for i in core), len(core)),
        "unmatched": sorted(
            f"{label.get(child, '?')} → {label.get(parent, '?')}"
            for (child, parent), pair in zip(pairs, predicted, strict=True)
            if pair not in valid
        ),
        "missedCore": [
            f"{entries[i]['child']} → {entries[i]['parent']}"
            for i in core
            if wanted[i] not in set(predicted)
        ],
    }


_COUNTS = STAGE_COUNTS


def _usage(
    gateway: ReplayGateway, labels: Sequence[str], elapsed: Mapping[str, float]
) -> dict[str, Any]:
    """Model calls per document and stage, per stage, and in total (of the labelled ones), and
    the seconds each document took from start to finish (`elapsed`)."""
    documents = {name: stages for name, stages in gateway.stats().items() if name in labels}
    stages: dict[str, dict[str, float]] = {}
    total = dict.fromkeys(_COUNTS, 0.0)
    for per_stage in documents.values():
        for purpose, numbers in per_stage.items():
            stage = stages.setdefault(purpose, dict.fromkeys(_COUNTS, 0.0))
            for key in _COUNTS:
                stage[key] += numbers[key]
                total[key] += numbers[key]

    def tidy(numbers: dict[str, float]) -> dict[str, Any]:
        return {
            key: round(value, 1) if key in ("seconds", "recordedSeconds") else int(value)
            for key, value in numbers.items()
        }

    return {
        "documents": documents,
        "stages": {purpose: tidy(numbers) for purpose, numbers in stages.items()},
        "total": tidy(total),
        "elapsed": {
            "documents": {label: elapsed[label] for label in labels if label in elapsed},
            "total": round(sum(elapsed.get(label, 0.0) for label in labels), 1),
        },
    }


SCENARIOS = ("sequential", "sameBaseline")
# Labels of the same-baseline scenario's documents, apart from the sequential ones in the usage.
_SAME_BASELINE = "{name} (same baseline)"


@dataclass(frozen=True)
class _Document:
    name: str
    chunks: list[ChunkText]


def _documents(files: Mapping[str, bytes]) -> list[_Document]:
    documents: list[_Document] = []
    for name in sorted(path for path in files if path.startswith("docs/")):
        data = files[name]
        parsed = parse_document(detect_type(name, data), data)
        if parsed.needs_vision:
            log(f"skip {name}: scanned PDF")
            continue
        chunks = [
            ChunkText(
                id=stable_id("chunk", name, str(seq)),
                seq=seq,
                text=chunk.text,
                page=chunk.page,
                heading=chunk.heading,
            )
            for seq, chunk in enumerate(chunk_pages(parsed.pages))
        ]
        documents.append(_Document(name, chunks))
    return documents


REVIEWS = ("acceptAll", "byFlags")
# Label of the sequential scenario's documents in the by-flags review, apart in the usage.
_BY_FLAGS = "{name} (by flags)"
# The thresholds the evaluation compares (spec 004, 4.1).
_THRESHOLDS = (0.5, 0.6)


def pending_of(
    label: str, proposals: Sequence[Proposal], known: Sequence[KnownElement]
) -> list[PendingType]:
    """The object types a change set proposes, as later documents see them while it is open."""
    by_ref = {p.temp_ref: p for p in proposals if p.op == "create" and p.temp_ref}
    labels = {str(element.id): element.label_zh for element in known}
    out: list[PendingType] = []
    for seq, proposal in enumerate(proposals, start=1):
        if proposal.op != "create" or proposal.kind != "entity_type":
            continue
        parent = proposal.fields.get("parentRef")
        parent_label = (
            by_ref[parent].fields["labelZh"] if parent in by_ref else labels.get(parent or "")
        )
        out.append(
            PendingType(
                item_id=item_id(label, seq),
                change_set_id=stable_id("changeset", label),
                change_set_title=label,
                label_zh=proposal.fields["labelZh"],
                label_en=proposal.fields.get("labelEn"),
                synonyms=tuple(s["text"] for s in proposal.fields["synonyms"]),
                definition_zh=proposal.fields.get("definitionZh"),
                parent_label=parent_label,
                members=tuple(
                    other.fields["labelZh"]
                    for other in proposals
                    if other.kind != "entity_type"
                    and other.fields.get("domainRef") == proposal.temp_ref
                ),
            )
        )
    return out


def _proposal_names(proposal: Proposal) -> set[str]:
    fields = proposal.fields
    values = [fields.get("labelZh") or "", fields.get("labelEn") or ""]
    values += [s["text"] for s in fields.get("synonyms") or []]
    return {normalize(value) for value in values if value}


class FlagReviewer:
    """The by-flags review (spec 004, section 10): a possible duplicate is merged when the
    other side is in the same expected group and kept apart otherwise; a type the model judged
    the same is kept apart when the other side is not in its group. Everything else is
    accepted as proposed."""

    def __init__(self, expected: Mapping[str, Any]) -> None:
        self.groups = [{normalize(n) for n in group["names"]} for group in expected["entity_types"]]
        self.items: dict[UUID, set[str]] = {}

    def remember(self, label: str, proposals: Sequence[Proposal]) -> None:
        for seq, proposal in enumerate(proposals, start=1):
            self.items[item_id(label, seq)] = _proposal_names(proposal)

    def decider(
        self, version: WorkingVersion, proposals: Sequence[Proposal]
    ) -> Callable[[Proposal, ProposedMatch], str | None]:
        by_ref = {p.temp_ref: p for p in proposals if p.temp_ref}

        def group(names: set[str]) -> int | None:
            return next((i for i, g in enumerate(self.groups) if names & g), None)

        def decide(proposal: Proposal, record: ProposedMatch) -> str | None:
            other: set[str] = set()
            if record.element_id is not None:
                element = next((e for e in version.elements if e.id == record.element_id), None)
                other = _names(element) if element is not None else set()
            elif record.item_id is not None:
                other = self.items.get(record.item_id, set())
            elif record.temp_ref in by_ref:
                other = _proposal_names(by_ref[record.temp_ref])
            mine = group(_proposal_names(proposal))
            together = mine is not None and mine == group(other)
            if record.kind == "possible":
                return "same" if together else "different"
            return None if together else "different"

        return decide


class OracleReviewer(FlagReviewer):
    """Decide create items against the expected answers, without a database."""

    def __init__(self, expected: Mapping[str, Any]) -> None:
        super().__init__(expected)
        self.expected = expected

    def review(
        self, proposals: Sequence[Proposal], label: str, version: WorkingVersion | None
    ) -> tuple[list[Proposal], list[DecidedItem]]:
        accepted: list[Proposal] = []
        decided: list[DecidedItem] = []
        known = {str(e.id): e for e in version.elements} if version is not None else {}
        review_labels = {
            ref: e.label_zh or e.label_en or e.local_name
            for ref, e in known.items()
            if e.kind == "entity_type"
        }
        groups = self.expected["entity_types"]
        group_of = {
            normalize(n): index for index, group in enumerate(groups) for n in group["names"]
        }

        def expected_group(ref: str | None) -> int | None:
            return group_of.get(normalize(review_labels.get(ref or "", "")))

        for seq, proposal in enumerate(proposals, start=1):
            fields = proposal.fields
            original_zh = fields.get("labelZh")
            original_en = fields.get("labelEn")
            final = proposal
            decision: Literal["accepted", "rejected"] = "accepted"
            if proposal.op == "create" and proposal.kind == "entity_type":
                candidate_names = [
                    normalize(value)
                    for value in (
                        original_zh or "",
                        original_en or "",
                        *(s["text"] for s in fields.get("synonyms") or []),
                    )
                    if value
                ]
                group = next((group_of[n] for n in candidate_names if n in group_of), None)
                if group is None:
                    decision = "rejected"
                elif normalize(original_zh or original_en or "") != normalize(
                    groups[group]["names"][0]
                ):
                    final = replace(
                        proposal, fields={**fields, "labelZh": groups[group]["names"][0]}
                    )
            elif proposal.op == "create" and proposal.kind == "relation_type":
                domain = expected_group(fields.get("domainRef"))
                range_ = expected_group(fields.get("rangeRef"))
                wanted = {
                    frozenset((group_of[normalize(r["domain"])], group_of[normalize(r["range"])]))
                    for r in self.expected["relations"]
                }
                if domain is None or range_ is None or frozenset((domain, range_)) not in wanted:
                    decision = "rejected"
            elif (
                proposal.op == "create"
                and proposal.kind == "property"
                and "properties" in self.expected
            ):
                domain = expected_group(fields.get("domainRef"))
                if not any(
                    domain == group_of[normalize(p["domain"])]
                    and _proposal_names(proposal) & {normalize(n) for n in p["names"]}
                    for p in self.expected["properties"]
                ):
                    decision = "rejected"
            if decision == "accepted":
                accepted.append(final)
                if final.temp_ref and final.kind == "entity_type":
                    review_labels[final.temp_ref] = (
                        final.fields.get("labelZh") or final.fields.get("labelEn") or ""
                    )
            match = proposal.match
            other_label = None
            if match is not None:
                other = known.get(str(match.element_id)) if match.element_id else None
                if other is not None:
                    other_label = other.label_zh
                elif match.item_id in self.items:
                    other_label = sorted(self.items[match.item_id])[0]
                elif match.temp_ref is not None:
                    other_label = review_labels.get(match.temp_ref)
            decided.append(
                DecidedItem(
                    item_id=item_id(label, seq),
                    kind=proposal.kind,
                    op=proposal.op,
                    decision=decision,
                    reject_reason="incorrect" if decision == "rejected" else None,
                    proposed_label_zh=original_zh,
                    proposed_label_en=original_en,
                    final_label_zh=final.fields.get("labelZh"),
                    final_label_en=final.fields.get("labelEn"),
                    # Memory keys use the endpoints that the merge actually applied.
                    domain_label=None,
                    range_label=None,
                    created_element_id=None,
                    renamed_element_id=None,
                    match_kind=match.kind if match else None,
                    match_decision=None,
                    match_other_label=other_label,
                    match_other_element_id=match.element_id if match else None,
                )
            )
        return accepted, decided


@dataclass(frozen=True)
class MemoryStep:
    before: ReviewMemory
    model: tuple[Proposal, ...]
    items: tuple[Proposal, ...]
    suppressed: tuple[tuple[str, str | None, str | None, UUID | None], ...]
    known: tuple[KnownElement, ...] = ()


class _CaptureGateway:
    def __init__(self, gateway: ReplayGateway, known: Sequence[KnownElement]) -> None:
        self.gateway = gateway
        self.known = known
        self.outputs: list[Proposal] = []
        self.term_batches: list[list[str]] = []
        self.found_types: list[EntityTypeOut] = []
        self.type_batch = 0

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
        effort: str | None = None,
    ) -> T:
        term_index = len(self.term_batches) if purpose == "extract.terms" else None
        if term_index is not None:
            self.term_batches.append([])
        result = await self.gateway.structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            files=files,
            document_id=document_id,
            effort=effort,
        )
        if term_index is not None:
            self.term_batches[term_index] = [term.name for term in cast(TermsOut, result).terms]
        elif purpose == "extract.types":
            unique_terms: dict[str, str] = {}
            for term_batch in self.term_batches:
                for name in term_batch:
                    key = normalize(name)
                    if key:
                        unique_terms.setdefault(key, name)
            terms = list(unique_terms.values())
            group = terms[
                self.type_batch * TYPES_BATCH_TERMS : (self.type_batch + 1) * TYPES_BATCH_TERMS
            ]
            context = types_context(self.known, group)
            aliases = _aliases(
                [str(element.id) for element in context]
                + [item.ref for item in self.found_types if _as_uuid(item.ref) is not None]
            )
            ids = {alias: value for value, alias in aliases.items()}
            type_batch_items = [
                item.model_copy(update={"ref": _unalias(item.ref, ids)})
                for item in cast(TypesOut, result).entity_types
            ]
            self.found_types = merge_types(self.found_types, type_batch_items)
            self.type_batch += 1
            for item in type_batch_items:
                self.outputs.append(
                    Proposal(
                        op="update" if _as_uuid(item.ref) is not None else "create",
                        kind="entity_type",
                        temp_ref=item.ref,
                        target_element_id=_as_uuid(item.ref),
                        fields={"labelZh": item.label_zh, "labelEn": item.label_en},
                    )
                )
        elif purpose == "extract.relations":
            _, aliases = relations_catalog(self.found_types, self.known)
            ids = {alias: value for value, alias in aliases.items()}
            values = result.model_dump()
            for item in values.get("relations", []):
                self.outputs.append(
                    Proposal(
                        op="create",
                        kind="relation_type",
                        fields={
                            "labelZh": item["label_zh"],
                            "domainRef": _unalias(item["domain"], ids),
                            "rangeRef": _unalias(item["range"], ids),
                        },
                    )
                )
            for item in values.get("properties", []):
                self.outputs.append(
                    Proposal(
                        op="create",
                        kind="property",
                        fields={
                            "labelZh": item["label_zh"],
                            "domainRef": _unalias(item["domain"], ids),
                        },
                    )
                )
        return result

    async def ping(self) -> bool:
        return await self.gateway.ping()


def _memory_key(proposal: Proposal, element_kind: str, step: MemoryStep) -> str | None:
    if proposal.op != "create" or proposal.kind != element_kind:
        return None
    fields = proposal.fields
    if proposal.kind == "entity_type":
        return type_key(fields.get("labelZh"), fields.get("labelEn"))
    names = {
        item.temp_ref: normalize(item.fields.get("labelZh") or item.fields.get("labelEn") or "")
        for item in step.model
        if item.kind == "entity_type"
    }
    names.update({str(e.id): normalize(e.label_zh or e.label_en or "") for e in step.known})
    domain = names.get(fields.get("domainRef"), "")
    label = normalize(fields.get("labelZh") or fields.get("labelEn") or "")
    if proposal.kind == "relation_type":
        return relation_key(domain, label, names.get(fields.get("rangeRef"), ""))
    return property_key(domain, label)


def _marked_pair(item: Proposal, step: MemoryStep, key: str) -> bool:
    if item.kind != "entity_type" or item.match is None:
        return False
    target = next((e.label_zh for e in step.known if e.id == item.match.element_id), None)
    if target is None:
        target = next(
            (p.fields.get("labelZh") for p in step.items if p.temp_ref == item.match.temp_ref),
            None,
        )
    own = normalize(item.fields.get("labelZh") or item.fields.get("labelEn") or "")
    return (
        item.match.kind in ("possible", "same")
        and bool(own and target)
        and pair_key(own, normalize(target or "")) == key
    )


def memory_metrics(
    steps: Sequence[MemoryStep], memory: ReviewMemory, *, enabled: bool
) -> dict[str, Any]:
    """Count opportunities from the memory visible before each later document."""
    counts: dict[str, list[int]] = {
        key: [0, 0]
        for key in (
            "reproposeModel",
            "reproposeReview",
            "variantRepropose",
            "renameReuse",
            "keptApartViolation",
        )
    }
    for step in steps:
        proposed = list(step.model)
        reviewed = list(step.items)
        suppressed = list(step.suppressed)
        for entry in step.before.entries:
            if entry.kind == "rejected":
                for metric in ("reproposeModel", "reproposeReview"):
                    counts[metric][1] += 1

                model_hit = any(
                    _memory_key(item, entry.element_kind, step) == entry.key for item in proposed
                )
                model_hit |= any(
                    kind == entry.element_kind
                    and (
                        memory_id == entry.id
                        or (kind == "entity_type" and type_key(zh, en) == entry.key)
                    )
                    for kind, zh, en, memory_id in suppressed
                )
                counts["reproposeModel"][0] += int(model_hit)
                counts["reproposeReview"][0] += int(
                    any(
                        _memory_key(item, entry.element_kind, step) == entry.key
                        for item in reviewed
                    )
                )
                variants = [
                    item
                    for item in reviewed
                    if item.op == "create"
                    and item.kind == entry.element_kind
                    and _memory_key(item, entry.element_kind, step) != entry.key
                ]
                counts["variantRepropose"][1] += len(variants)
                counts["variantRepropose"][0] += sum(
                    candidate_score(
                        Names.of(item.fields.get("labelZh"), item.fields.get("labelEn"), ()),
                        Names.of(entry.label, entry.label_en, ()),
                    ).value
                    >= THRESHOLD
                    for item in variants
                )
            elif entry.kind == "renamed":
                related = [
                    item
                    for item in proposed
                    if item.kind == "entity_type"
                    and (
                        type_key(item.fields.get("labelZh"), item.fields.get("labelEn"))
                        in {entry.key, type_key(entry.to_label_zh, entry.to_label_en)}
                        or item.target_element_id == entry.element_id
                        or (item.match is not None and item.match.element_id == entry.element_id)
                    )
                ]
                counts["renameReuse"][1] += len(related)
                counts["renameReuse"][0] += sum(
                    type_key(item.fields.get("labelZh"), item.fields.get("labelEn"))
                    == type_key(entry.to_label_zh, entry.to_label_en)
                    or item.target_element_id == entry.element_id
                    or (item.match is not None and item.match.element_id == entry.element_id)
                    for item in related
                )
            elif entry.kind == "kept_apart":
                names = {
                    normalize(item.fields.get("labelZh") or item.fields.get("labelEn") or "")
                    for item in proposed
                    if item.kind == "entity_type"
                }
                known_names = {normalize(item.label_zh) for item in step.known}
                first = normalize(entry.label)
                other = normalize(entry.other_label or "")
                if (
                    first
                    and other
                    and (
                        (first in names and other in names | known_names)
                        or (other in names and first in names | known_names)
                    )
                ):
                    counts["keptApartViolation"][1] += 1
                    counts["keptApartViolation"][0] += int(
                        any(_marked_pair(item, step, entry.key) for item in reviewed)
                    )
    return {
        "enabled": enabled,
        "entries": len(memory.entries),
        **{
            key: {"numerator": n, "denominator": d, "ratio": _ratio(n, d)}
            for key, (n, d) in counts.items()
        },
    }


def resolve_counts(
    pairs: Sequence[JudgedPair], expected: Mapping[str, Any] | None, trimmed: Counter[str]
) -> dict[str, Any]:
    """The pairs the resolve calls judged, overall and in the band between the thresholds."""
    groups = (
        [{normalize(n) for n in g["names"]} for g in expected["entity_types"]] if expected else []
    )

    def together(pair: JudgedPair) -> bool | None:
        if not groups:
            return None
        a = {normalize(n) for n in pair.names if n}
        b = {normalize(n) for n in pair.candidate_names if n}
        mine = next((i for i, g in enumerate(groups) if a & g), None)
        return mine is not None and mine == next((i for i, g in enumerate(groups) if b & g), None)

    def summary(selected: Sequence[JudgedPair]) -> dict[str, Any]:
        verdicts = Counter(str(pair.verdict) for pair in selected)
        out: dict[str, Any] = {"pairs": len(selected), "verdicts": dict(sorted(verdicts.items()))}
        if groups:
            out["sameGroup"] = sum(together(pair) is True for pair in selected)
            out["sameJudgedRight"] = sum(
                pair.verdict == "same" and together(pair) is True for pair in selected
            )
            out["sameJudgedWrong"] = sum(
                pair.verdict == "same" and together(pair) is False for pair in selected
            )
        return out

    low, high = _THRESHOLDS
    return {
        "all": summary(pairs),
        # Every pair not judged different, to read what the model merged or doubted.
        "notDifferent": [
            f"{p.names[0]} / {p.candidate_names[0]}: {p.verdict}"
            for p in pairs
            if p.verdict != "different"
        ],
        "band": {
            "from": low,
            "below": high,
            **summary([p for p in pairs if low <= p.score < high]),
            "examples": sorted(
                f"{p.names[0]} / {p.candidate_names[0]}: {p.verdict}"
                for p in pairs
                if low <= p.score < high
            )[:40],
        },
        "trimmed": dict(sorted(trimmed.items())),
    }


_LITERAL_KINDS = {
    "entityTypes": "entity_type",
    "relations": "relation_type",
    "properties": "property",
}


def literal_share(counts: Counter[str]) -> dict[str, Any]:
    """The share of items whose cited sentence names them (spec 004, 7.2 and 10, item 7):
    per kind, and over all checked items (`all`), with the number checked (`checked`) and
    the relations kept only with their table's name and header row (`relationsByTable`, #60)."""
    out: dict[str, Any] = {
        name: _ratio(counts[f"{kind}:ok"], counts[kind]) for name, kind in _LITERAL_KINDS.items()
    }
    total = sum(counts[kind] for kind in _LITERAL_KINDS.values())
    passed = sum(counts[f"{kind}:ok"] for kind in _LITERAL_KINDS.values())
    out["all"] = _ratio(passed, total)
    out["checked"] = total
    out["relationsByTable"] = counts["relation_type:table"]
    return out


def shortlist_recall(expected: Mapping[str, Any]) -> dict[str, Any]:
    """The free lower bound of the shortlist's recall (spec 004, 4.1), per threshold."""
    groups = [group["names"] for group in expected["entity_types"]]
    out: dict[str, Any] = {}
    for threshold in _THRESHOLDS:
        hits, total = group_recall(groups, threshold)
        out[str(threshold)] = {"pairs": total, "candidates": hits, "recall": _ratio(hits, total)}
    return out


async def run_case(
    files: Mapping[str, bytes],
    gateway: ReplayGateway,
    models: ExtractionModels,
    scenarios: Sequence[str] = SCENARIOS,
    *,
    reviewed: bool = False,
    no_memory: bool = False,
) -> dict[str, Any]:
    """Runs a case; without eval/expected.toml it only counts what was found (`scored` false).

    The sequential scenario merges each document's change set before identifying the next one;
    its result is the top level. The same-baseline one (`sameBaseline`) identifies every
    document against the starting ontology first, each seeing the earlier ones' items as
    pending, and merges the change sets in order after, as when documents are uploaded together
    and reviewed later (spec 004, section 10). Both are reported for a reviewer who accepts
    everything and, with expected answers, for one who follows the flags (`byFlags`); in the
    sequential scenario the latter is a run of its own, since merging decides what later
    documents see.
    """
    # The sequential scenario is the one comparable with the baselines: it always runs.
    if "sequential" not in scenarios or set(scenarios) - set(SCENARIOS):
        raise ValueError(f"Scenarios must be sequential and optionally sameBaseline: {scenarios}")
    answers = files.get("eval/expected.toml")
    # Checked before paying for any call.
    expected = parse_expected(answers.decode("utf-8")) if answers is not None else None
    if reviewed and expected is None:
        raise ExpectedError("reviewed evaluation needs eval/expected.toml")
    documents = _documents(files)
    extractor = Extractor(gateway, models)
    pairs: dict[str, list[JudgedPair]] = {}
    trimmed: dict[str, Counter[str]] = {}
    literal: dict[str, Counter[str]] = {}
    elapsed: dict[str, float] = {}

    async def identify(
        document: _Document,
        label: str,
        version: WorkingVersion,
        scenario: str,
        pending: Sequence[PendingType] = (),
        memory: ReviewMemory | None = None,
        outcome: MemoryOutcome | None = None,
        model_output: list[Proposal] | None = None,
    ) -> list[Proposal]:
        document_id = stable_id("document", label)
        gateway.label(document_id, label)
        log(
            f"{label}: {len(document.chunks)} chunks, "
            f"{sum(len(c.text) for c in document.chunks)} characters"
        )

        async def progress(step: str, done: int, total: int) -> None:
            log(f"    {step} {done}/{total}")

        started = time.monotonic()
        stats = RunStats()
        capture = _CaptureGateway(gateway, version.known()) if model_output is not None else None
        running_extractor = Extractor(capture, models) if capture is not None else extractor
        proposals = await running_extractor.run(
            document_id=document_id,
            title=document.name,
            chunks=document.chunks,
            known=version.known(),
            progress=progress,
            pending=pending,
            stats=stats,
            memory=memory,
            outcome=outcome,
        )
        if capture is not None and model_output is not None:
            model_output.extend(capture.outputs)
        # From start to finish: with batches called at the same time, less than the sum of the
        # calls' seconds in the usage.
        elapsed[label] = round(time.monotonic() - started, 1)
        log(f"    {elapsed[label]:.1f} s")
        pairs.setdefault(scenario, []).extend(stats.pairs)
        trimmed.setdefault(scenario, Counter()).update(stats.trimmed)
        literal.setdefault(scenario, Counter()).update(stats.literal)
        return proposals

    async def sequential(review: str) -> tuple[WorkingVersion, list[str], list[Proposal]]:
        version = WorkingVersion()
        reviewer = FlagReviewer(expected) if expected is not None else None
        skipped: list[str] = []
        proposed: list[Proposal] = []
        for document in documents:
            label = document.name if review == "acceptAll" else _BY_FLAGS.format(name=document.name)
            proposals = await identify(document, label, version, f"sequential/{review}")
            proposed += proposals
            decide = None
            if review == "byFlags" and reviewer is not None:
                reviewer.remember(label, proposals)
                decide = reviewer.decider(version, proposals)
            skipped += version.merge(proposals, label, decide)
        return version, skipped, proposed

    async def reviewed_sequential() -> tuple[
        WorkingVersion, list[str], list[Proposal], dict[str, Any]
    ]:
        if expected is None:
            raise ExpectedError("reviewed evaluation needs eval/expected.toml")
        version = WorkingVersion()
        reviewer = OracleReviewer(expected)
        memory = ReviewMemory(stable_id("eval-memory"), ())
        steps: list[MemoryStep] = []
        skipped: list[str] = []
        proposed: list[Proposal] = []
        for index, document in enumerate(documents):
            label = document.name
            before = memory
            outcome = MemoryOutcome()
            model_output: list[Proposal] = []
            known_before = tuple(version.known())
            proposals = await identify(
                document,
                label,
                version,
                "sequential/reviewed",
                memory=memory if not no_memory else ReviewMemory(memory.ontology_id, ()),
                outcome=outcome,
                model_output=model_output,
            )
            proposed.extend(proposals)
            accepted, decisions = reviewer.review(proposals, label, version)
            reviewer.remember(label, accepted)
            decide = reviewer.decider(version, accepted)
            old_ids = {element.id for element in version.elements}
            skipped += version.merge(accepted, label, decide)
            accepted_decisions = (d for d in decisions if d.decision == "accepted")
            completed: list[DecidedItem] = []
            by_id = {str(element.id): element for element in version.elements}
            applied_refs = {
                proposal.temp_ref: version.recorded[item_id(label, seq)].merged_into
                for seq, proposal in enumerate(accepted, start=1)
                if proposal.kind == "entity_type" and proposal.temp_ref
            }

            def ref_name(
                ref: str | None,
                elements: Mapping[str, KnownElement],
                refs: Mapping[str, UUID | None],
            ) -> str | None:
                if ref is None:
                    return None
                element = elements.get(str(refs.get(ref) or ref))
                return (
                    element.label_zh or element.label_en or element.local_name
                    if element is not None
                    else None
                )

            def endpoint_names(
                proposal: Proposal,
                target: KnownElement | None,
                elements: Mapping[str, KnownElement],
                refs: Mapping[str, UUID | None],
            ) -> tuple[str | None, str | None]:
                domain = (
                    str(target.domain_id)
                    if target and target.domain_id
                    else proposal.fields.get("domainRef")
                )
                range_ = (
                    str(target.range_id)
                    if target and target.range_id
                    else proposal.fields.get("rangeRef")
                )
                return ref_name(domain, elements, refs), ref_name(range_, elements, refs)

            for seq, decided in enumerate(accepted_decisions, start=1):
                record = version.recorded[item_id(label, seq)]
                made = record.merged_into
                proposal = accepted[seq - 1]
                target = by_id.get(str(made)) if made is not None else None
                domain_label, range_label = endpoint_names(proposal, target, by_id, applied_refs)
                match_decision = (
                    cast(Literal["same", "different"] | None, decide(proposal, proposal.match))
                    if proposal.match is not None
                    else None
                )
                completed.append(
                    replace(
                        decided,
                        item_id=item_id(label, seq),
                        created_element_id=made if made not in old_ids else None,
                        final_label_zh=target.label_zh if target else decided.final_label_zh,
                        final_label_en=target.label_en if target else decided.final_label_en,
                        domain_label=domain_label,
                        range_label=range_label,
                        match_decision=match_decision,
                    )
                )
            for proposal, decided in zip(proposals, decisions, strict=True):
                if decided.decision != "rejected":
                    continue
                domain_label, range_label = endpoint_names(proposal, None, by_id, applied_refs)
                if proposal.kind in ("relation_type", "property") and domain_label is None:
                    continue
                if proposal.kind == "relation_type" and range_label is None:
                    continue
                # Rejected and accepted item ids can coincide; collect uses them only as provenance.
                completed.append(
                    replace(decided, domain_label=domain_label, range_label=range_label)
                )
            memory = apply_delta(
                memory,
                collect("ai_extraction", completed),
                now=_EPOCH + timedelta(seconds=index),
                max_entries=500,
            )
            steps.append(
                MemoryStep(
                    before,
                    tuple(model_output),
                    tuple(proposals),
                    tuple(
                        (s.kind, s.label_zh, s.label_en, s.memory_entry_id)
                        for s in outcome.suppressed
                    ),
                    known_before,
                )
            )
        return version, skipped, proposed, memory_metrics(steps, memory, enabled=not no_memory)

    if reviewed:
        version, skipped, proposed, memory_result = await reviewed_sequential()
    else:
        version, skipped, proposed = await sequential("acceptAll")
    labels = [document.name for document in documents]
    result = _scenario(version, skipped, proposed, expected, _usage(gateway, labels, elapsed))
    if reviewed:
        result["merge"]["review"] = "oracle"
    scenario_key = "sequential/reviewed" if reviewed else "sequential/acceptAll"
    result["resolve"] = resolve_counts(pairs[scenario_key], expected, trimmed[scenario_key])
    result["literalShare"] = literal_share(literal[scenario_key])
    if reviewed:
        result["memory"] = memory_result
    if expected is not None:
        result["shortlistRecall"] = shortlist_recall(expected)
        if not reviewed:
            version, skipped, proposed = await sequential("byFlags")
            labels = [_BY_FLAGS.format(name=document.name) for document in documents]
            result["byFlags"] = _review(
                version, skipped, expected, _usage(gateway, labels, elapsed)
            )
    if "sameBaseline" in scenarios:
        baseline = WorkingVersion()
        identified: list[tuple[str, list[Proposal]]] = []
        for document in documents:
            label = _SAME_BASELINE.format(name=document.name)
            pending = [
                item
                for earlier, proposals in identified
                for item in pending_of(earlier, proposals, baseline.elements)
            ]
            proposals = await identify(document, label, baseline, "sameBaseline", pending)
            identified.append((label, proposals))
        labels = [label for label, _ in identified]
        reviews = REVIEWS if expected is not None else REVIEWS[:1]
        outcomes: dict[str, tuple[WorkingVersion, list[str]]] = {}
        for review in reviews:
            version, skipped = baseline.copy(), []
            reviewer = FlagReviewer(expected) if expected is not None else None
            for label, proposals in identified:
                decide = None
                if review == "byFlags" and reviewer is not None:
                    reviewer.remember(label, proposals)
                    decide = reviewer.decider(version, proposals)
                skipped += version.merge(proposals, label, decide)
            outcomes[review] = (version, skipped)
        version, skipped = outcomes["acceptAll"]
        same = _scenario(
            version,
            skipped,
            [p for _, proposals in identified for p in proposals],
            expected,
            _usage(gateway, labels, elapsed),
        )
        same["resolve"] = resolve_counts(pairs["sameBaseline"], expected, trimmed["sameBaseline"])
        same["literalShare"] = literal_share(literal["sameBaseline"])
        if "byFlags" in outcomes and expected is not None:
            version, skipped = outcomes["byFlags"]
            same["byFlags"] = _review(version, skipped, expected, None)
        result["sameBaseline"] = same
    result["models"] = asdict(models)
    return result


def _review(
    version: WorkingVersion,
    skipped: Sequence[str],
    expected: dict[str, Any],
    usage: dict[str, Any] | None,
) -> dict[str, Any]:
    """The scores and merge counts of the by-flags review."""
    scored = score(version.elements, expected, version.parents)
    out: dict[str, Any] = {
        section: {
            key: value
            for key, value in scored[section].items()
            if key in ("predicted", "precision", "recall")
        }
        for section in ("entityTypes", "relations", "properties", "hierarchy")
    }
    out["merge"] = {**merge_counts(version, skipped, expected), "review": "byFlags"}
    if usage is not None:
        out["usage"] = usage["total"]
    return out


def _scenario(
    version: WorkingVersion,
    skipped: Sequence[str],
    proposals: Sequence[Proposal],
    expected: dict[str, Any] | None,
    usage: dict[str, Any],
) -> dict[str, Any]:
    known, parents = version.elements, version.parents
    if expected is not None:
        result = {"scored": True, **score(known, expected, parents)}
    else:
        types = {e.id for e in known if e.kind == "entity_type"}
        result = {
            "scored": False,
            "entityTypes": {"predicted": len(types)},
            "relations": {"predicted": sum(e.kind == "relation_type" for e in known)},
            "properties": {"predicted": sum(e.kind == "property" for e in known)},
            "hierarchy": {"predicted": sum(child in types for child in parents)},
        }
    ungrounded = sum("evidence_not_found" in p.flags for p in proposals)
    result["proposals"] = len(proposals)
    result["groundedShare"] = round(1 - ungrounded / len(proposals), 3) if proposals else None
    result["aligned"] = dict(
        sorted(Counter(p.match.kind for p in proposals if p.match is not None).items())
    )
    result["merge"] = merge_counts(version, skipped, expected)
    result["usage"] = usage
    result["elements"] = dump_elements(known)
    result["parents"] = {str(child): str(parent) for child, parent in parents.items()}
    return result


def _models(settings: Settings, mode: str, manifest: str | None) -> ExtractionModels:
    if mode == "replay" and manifest:
        return ExtractionModels(**json.loads(manifest)["models"])
    return ExtractionModels.of(settings)


def evaluate(
    bundle: dict[str, Any],
    inner: ModelGateway | None = None,
    write_line: Callable[[dict[str, Any]], None] = write_json_line,
) -> tuple[dict[str, Any], int]:
    """Runs a bundle; returns the object for stdout and the exit code.

    `inner` is the gateway for calls that were not recorded ("record" only); by default the
    real one.
    """
    mode = bundle.get("mode", "record")
    if mode not in {"record", "replay"}:
        raise ValueError(f"Unknown mode: {mode}")
    settings = Settings()
    scenarios = bundle.get("scenarios") or SCENARIOS
    if not isinstance(scenarios, list | tuple) or not all(isinstance(s, str) for s in scenarios):
        raise ValueError(f"Scenarios must be a list of names: {scenarios!r}")
    reviewed = bundle.get("reviewed", False)
    no_memory = bundle.get("noMemory", False)
    if not isinstance(reviewed, bool):
        raise ValueError(f"reviewed must be boolean: {reviewed!r}")
    if not isinstance(no_memory, bool):
        raise ValueError(f"noMemory must be boolean: {no_memory!r}")
    models = _models(settings, mode, bundle.get("manifest"))
    files = {path: base64.b64decode(value) for path, value in bundle["files"].items()}
    if mode == "replay":
        inner = None
    elif inner is None:
        inner = MeteredGateway(settings)
    recordings = load_recordings(
        bundle.get("recordings", []),
        on_invalid=lambda index: log(f"recording {index} is not readable, skipped"),
    )
    stream = RecordingStream(json.dumps({"models": asdict(models)}, indent=1), write_line)
    gateway = ReplayGateway(recordings, inner, on_record=stream.on_record)
    try:
        result = asyncio.run(
            run_case(files, gateway, models, scenarios, reviewed=reviewed, no_memory=no_memory)
        )
    except (AiError, ReplayMissError, ExpectedError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        return {"type": "error", "error": error}, 1
    except Exception as exc:
        traceback.print_exc()
        return {"type": "error", "error": type(exc).__name__}, 1
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"type": "result", "result": text}, 0


def main() -> int:
    bundle = json.loads(sys.stdin.read())
    if "--rescore" in sys.argv[1:]:
        known = load_elements(bundle["elements"])
        parents = {UUID(c): UUID(p) for c, p in bundle.get("parents", {}).items()}
        expected = parse_expected(bundle["expected"])
        print(json.dumps(score(known, expected, parents), ensure_ascii=False))
        return 0
    output, code = evaluate(bundle)
    write_json_line(output)
    return code


if __name__ == "__main__":
    sys.exit(main())
