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

Progress goes to stderr. Stdout is one JSON object: {"result": "<result JSON text>",
"files": [{"name": ..., "content": ...}]} with the new recording files, or {"error": ...,
"files": [...]} when the run failed, so that calls already paid for are kept.

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
from typing import Any, cast
from uuid import UUID, uuid5

from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    Extractor,
    KnownElement,
    Proposal,
    normalize,
)
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.pipeline import to_item
from ontology_platform.modules.ai.replay import (
    MeteredGateway,
    ReplayGateway,
    ReplayMissError,
    load_recordings,
)
from ontology_platform.modules.documents.chunking import chunk_pages
from ontology_platform.modules.documents.parsers import detect_type, parse_document
from ontology_platform.modules.ontology.schemas import ElementFields
from ontology_platform.modules.ontology.service import (
    PlanElement,
    PlanItem,
    Resolution,
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
        # Flags of the item that created an element: whether a duplicate was marked.
        self.flags: dict[UUID, tuple[str, ...]] = {}

    def copy(self) -> "WorkingVersion":
        other = WorkingVersion()
        other.elements, other.parents, other.flags = (
            list(self.elements),
            dict(self.parents),
            dict(self.flags),
        )
        return other

    def merge(self, proposals: Sequence[Proposal]) -> list[str]:
        """Merges one change set with every item accepted; returns the codes of skipped items."""
        items = [
            PlanItem(
                id=stable_id("item", str(seq)),
                seq=seq,
                op=proposal.op,
                kind=proposal.kind,
                decision="accepted",
                temp_ref=proposal.temp_ref,
                target_element_id=proposal.target_element_id,
                target_revision=proposal.target_revision,
                fields=to_item(proposal, _EVAL_DOCUMENT).proposed,
                edited=False,
            )
            for seq, proposal in enumerate(proposals, start=1)
        ]
        plan = plan_merge(items, self._plan_elements(), base_iri=BASE_IRI)
        proposal_of = {item.id: proposal for item, proposal in zip(items, proposals, strict=True)}
        creates = {item.temp_ref: item for item in items if item.op == "create" and item.temp_ref}
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
                    item, proposal_of[item.id], plan.get(item.id), resolve
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

        for item in items:
            apply(item)
        # New elements keep the order of their items, whatever order dependencies made them in.
        seq_of = {made[item.id]: item.seq for item in items if item.id in made}
        self.elements[start:] = sorted(self.elements[start:], key=lambda e: seq_of[e.id])
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
        self.flags[element_id] = tuple(proposal.flags)
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
    same Chinese label), marked (a member was proposed as a possible duplicate) or unmarked.
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
    }
    if expected is None:
        return counts
    groups = [{normalize(n) for n in group["names"]} for group in expected["entity_types"]]
    members: dict[int, list[KnownElement]] = {}
    for element in version.elements:
        if element.kind != "entity_type":
            continue
        names = _names(element)
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
        and any("possible_duplicate" in version.flags.get(e.id, ()) for e in found)
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
            }
        )
        for item in saved
    ]


def _names(element: KnownElement) -> set[str]:
    values = {element.label_zh, element.local_name, *element.synonyms}
    if element.label_en:
        values.add(element.label_en)
    return {normalize(value) for value in values if value}


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


_COUNTS = ("calls", "replayed", "seconds", "inputTokens", "outputTokens")


def _usage(gateway: ReplayGateway, labels: Sequence[str]) -> dict[str, Any]:
    """Model calls per document and stage, per stage, and in total (of the labelled ones)."""
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
            key: round(value, 1) if key == "seconds" else int(value)
            for key, value in numbers.items()
        }

    return {
        "documents": documents,
        "stages": {purpose: tidy(numbers) for purpose, numbers in stages.items()},
        "total": tidy(total),
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


async def run_case(
    files: Mapping[str, bytes],
    gateway: ReplayGateway,
    models: ExtractionModels,
    scenarios: Sequence[str] = SCENARIOS,
) -> dict[str, Any]:
    """Runs a case; without eval/expected.toml it only counts what was found (`scored` false).

    The sequential scenario merges each document's change set before identifying the next one;
    its result is the top level. The same-baseline one (`sameBaseline`) identifies every
    document against the starting ontology first and merges the change sets in order after,
    as when documents are uploaded together and reviewed later (spec 004, section 10).
    """
    # The sequential scenario is the one comparable with the baselines: it always runs.
    if "sequential" not in scenarios or set(scenarios) - set(SCENARIOS):
        raise ValueError(f"Scenarios must be sequential and optionally sameBaseline: {scenarios}")
    answers = files.get("eval/expected.toml")
    # Checked before paying for any call.
    expected = parse_expected(answers.decode("utf-8")) if answers is not None else None
    documents = _documents(files)
    extractor = Extractor(gateway, models)

    async def identify(document: _Document, label: str, version: WorkingVersion) -> list[Proposal]:
        document_id = stable_id("document", label)
        gateway.label(document_id, label)
        log(
            f"{label}: {len(document.chunks)} chunks, "
            f"{sum(len(c.text) for c in document.chunks)} characters"
        )

        async def progress(step: str, done: int, total: int) -> None:
            log(f"    {step} {done}/{total}")

        started = time.monotonic()
        proposals = await extractor.run(
            document_id=document_id,
            title=document.name,
            chunks=document.chunks,
            known=version.elements,
            progress=progress,
        )
        log(f"    {time.monotonic() - started:.1f} s")
        return proposals

    version = WorkingVersion()
    skipped: list[str] = []
    proposed: list[Proposal] = []
    for document in documents:
        proposals = await identify(document, document.name, version)
        proposed += proposals
        skipped += version.merge(proposals)
    labels = [document.name for document in documents]
    result = _scenario(version, skipped, proposed, expected, _usage(gateway, labels))
    if "sameBaseline" in scenarios:
        baseline = WorkingVersion()
        identified = [
            await identify(document, _SAME_BASELINE.format(name=document.name), baseline)
            for document in documents
        ]
        version, skipped = baseline.copy(), []
        for proposals in identified:
            skipped += version.merge(proposals)
        labels = [_SAME_BASELINE.format(name=document.name) for document in documents]
        same = _scenario(
            version,
            skipped,
            [p for proposals in identified for p in proposals],
            expected,
            _usage(gateway, labels),
        )
        result["sameBaseline"] = same
    result["models"] = asdict(models)
    return result


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
    result["merge"] = merge_counts(version, skipped, expected)
    result["usage"] = usage
    result["elements"] = dump_elements(known)
    result["parents"] = {str(child): str(parent) for child, parent in parents.items()}
    return result


def _models(settings: Settings, mode: str, manifest: str | None) -> ExtractionModels:
    if mode == "replay" and manifest:
        return ExtractionModels(**json.loads(manifest)["models"])
    return ExtractionModels(standard=settings.ai_model, reasoning=settings.ai_reasoning_model)


def _files(gateway: ReplayGateway, models: ExtractionModels) -> list[dict[str, str]]:
    files = [{"name": name, "content": text} for name, text in gateway.recording_files()]
    # Only a run that recorded something says which models the recordings are for: a run that
    # failed before its first answer (no key, wrong model) must not redirect later replays.
    if files:
        manifest = json.dumps({"models": asdict(models)}, indent=1)
        files.append({"name": MANIFEST, "content": manifest})
    return files


def evaluate(
    bundle: dict[str, Any], inner: ModelGateway | None = None
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
    gateway = ReplayGateway(recordings, inner)
    try:
        result = asyncio.run(run_case(files, gateway, models, scenarios))
    except (AiError, ReplayMissError, ExpectedError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        return {"error": error, "files": _files(gateway, models)}, 1
    except Exception as exc:
        traceback.print_exc()
        return {"error": type(exc).__name__, "files": _files(gateway, models)}, 1
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"result": text, "files": _files(gateway, models)}, 0


def main() -> int:
    bundle = json.loads(sys.stdin.read())
    if "--rescore" in sys.argv[1:]:
        known = load_elements(bundle["elements"])
        parents = {UUID(c): UUID(p) for c, p in bundle.get("parents", {}).items()}
        expected = parse_expected(bundle["expected"])
        print(json.dumps(score(known, expected, parents), ensure_ascii=False))
        return 0
    output, code = evaluate(bundle)
    print(json.dumps(output, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
