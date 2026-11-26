"""Request and result models for metric evaluation and rule checks."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from ontology_platform.modules.ontology.schemas import MetricAggregate
from ontology_platform.modules.query import schemas as query
from ontology_platform.schemas import CamelModel


class KeySet(CamelModel):
    type_id: UUID
    keys: list[str] = Field(max_length=100)

    def to_key_set(self) -> query.KeySet:
        return query.KeySet(type_id=self.type_id, keys=tuple(self.keys))


class MetricInfo(CamelModel):
    metric_id: UUID
    label: str
    definition: str | None
    unit: str | None
    subject_type_id: UUID
    subject_type_label: str
    aggregate: MetricAggregate
    bound: bool


class MetricList(CamelModel):
    release: query.ReleaseRef
    items: list[MetricInfo]


class MetricEvaluate(CamelModel):
    within: KeySet | None = None


class MetricValue(CamelModel):
    release: query.ReleaseRef
    metric_id: UUID
    label: str
    unit: str | None
    aggregate: MetricAggregate
    value: str | None
    display: str | None
    population: int
    matched: int | None
    nulls: int
    reason: Literal["empty_population"] | None
    steps: list[query.StepOut]


RuleCheck = Literal[
    "minCount",
    "minInclusive",
    "maxInclusive",
    "minExclusive",
    "maxExclusive",
    "allowedValues",
    "minLength",
    "maxLength",
    "pattern",
]
UncheckedReason = Literal[
    "path_not_property", "path_not_bound", "check_not_supported", "value_mismatch"
]


class Unchecked(CamelModel):
    check: str
    reason: UncheckedReason


class FailedCheck(CamelModel):
    check: RuleCheck
    expected: query.Scalar | list[query.Scalar]
    actual: query.Scalar | None


class RuleSample(CamelModel):
    object: query.ObjectRow
    failed: list[FailedCheck]


class RuleResult(CamelModel):
    constraint_id: UUID
    constraint_label: str
    property_id: UUID | None
    property_label: str | None
    checks: list[RuleCheck]
    unchecked: list[Unchecked]
    message: str | None
    violations: int
    samples: list[RuleSample]


class RuleCheckRequest(CamelModel):
    type_id: UUID
    within: KeySet | None = None
    limit: int = Field(
        default_factory=lambda: query.PAGE_DEFAULT,
        ge=1,
        le=query.PAGE_MAX,
        description="Maximum number of violation samples per rule. Defaults to 50.",
    )


class RuleReport(CamelModel):
    release: query.ReleaseRef
    type_id: UUID
    scanned: int
    checked_rules: int
    unchecked_rules: int
    results: list[RuleResult]
    steps: list[query.StepOut]
