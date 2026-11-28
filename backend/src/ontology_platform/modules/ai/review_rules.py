"""Deterministic review warnings."""

from uuid import UUID

from ontology_platform.modules.ai import candidates, schemas
from ontology_platform.modules.ontology import rules
from ontology_platform.modules.ontology.review_context import ReviewContext, ReviewItem
from ontology_platform.modules.ontology.review_memory import MemoryEntry


def similar_to_rejected(
    item: ReviewItem, entries: tuple[MemoryEntry, ...], *, threshold: float = candidates.THRESHOLD
) -> MemoryEntry | None:
    names = candidates.Names.of(item.label_zh, item.label_en, ())
    for entry in entries:
        if entry.element_kind != item.kind:
            continue
        other = candidates.Names.of(entry.label, entry.label_en, ())
        if candidates.main_name(item.label_zh, item.label_en) == candidates.main_name(
            entry.label, entry.label_en
        ):
            continue
        if candidates.score(names, other, threshold).value >= threshold:
            return entry
    return None


def rule_risks(
    ctx: ReviewContext, *, threshold: float = candidates.THRESHOLD
) -> dict[UUID, tuple[schemas.AssistRisk, ...]]:
    result: dict[UUID, tuple[schemas.AssistRisk, ...]] = {}
    for item in ctx.items:
        found: list[schemas.AssistRisk] = []

        def add(
            code: schemas.RiskCode,
            detail: schemas.RuleDetail,
            memory: UUID | None = None,
            found: list[schemas.AssistRisk] = found,
        ) -> None:
            found.append(
                schemas.AssistRisk(
                    code=code,
                    source="rule",
                    detail=detail,
                    reason=None,
                    related_item_ids=[],
                    related_element_ids=[],
                    memory_entry_id=memory,
                )
            )

        if "evidence_not_found" in item.flags:
            add("weak_evidence", "evidence_not_found")
        if item.op == "create" and not item.has_evidence:
            add("weak_evidence", "no_evidence")
        if item.confidence is not None and item.confidence < 0.5:
            add("weak_evidence", "low_confidence")
        if "possible_duplicate" in item.flags:
            add("duplicate", "possible_duplicate")
        if item.match_kind == "possible" and item.match_decision is None:
            add("duplicate", "undecided_match")
        if item.kept_fields:
            add("conflict", "kept_fields")
        if item.target_stale:
            add("conflict", "stale_target")
        name = item.local_name
        if not name or (
            not rules.LOCAL_NAME.fullmatch(name)
            or len(name) > rules.LOCAL_NAME_MAX_LENGTH
            or (item.kind == "entity_type" and not name[0].isupper())
            or (item.kind != "entity_type" and not name[0].islower())
        ):
            add("naming", "local_name_style")
        if item.op == "create" and not item.label_en:
            add("naming", "missing_label_en")
        if memory := similar_to_rejected(item, ctx.rejected, threshold=threshold):
            add("memory", "similar_to_rejected", memory.id)
        result[item.id] = tuple(found)
    return result
