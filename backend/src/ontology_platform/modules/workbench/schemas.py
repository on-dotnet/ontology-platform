"""API models of the workbench (docs/specs/001-m1-api-shapes.md)."""

from datetime import datetime

from ontology_platform.schemas import CamelModel


class Activity(CamelModel):
    id: str
    action: str
    occurred_at: datetime
    actor_name: str | None
    target_type: str | None
    target_id: str | None


class WorkbenchSummary(CamelModel):
    pending_change_sets: int
    entity_types: int
    processing_documents: int
    recent_activity: list[Activity]
