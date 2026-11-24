"""Read-only audit data for other modules (the workbench's recent activity)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditEventInfo:
    id: int
    occurred_at: datetime
    actor_id: UUID | None
    action: str
    target_type: str | None
    target_id: str | None
