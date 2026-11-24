"""Audit recording. Events join the caller's transaction and persist when it commits."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.audit.schemas import AuditEventInfo


def record(
    db: AsyncSession,
    action: str,
    *,
    actor_id: UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: Mapping[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    event = AuditEvent(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        detail=dict(detail or {}),
        ip=ip,
    )
    db.add(event)


async def recent(
    db: AsyncSession, *, prefixes: Sequence[str], limit: int = 10
) -> list[AuditEventInfo]:
    """The latest events whose action starts with one of `prefixes`, newest first."""
    statement = (
        select(AuditEvent)
        .where(or_(*(AuditEvent.action.startswith(prefix) for prefix in prefixes)))
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return [
        AuditEventInfo(
            id=event.id,
            occurred_at=event.occurred_at,
            actor_id=event.actor_id,
            action=event.action,
            target_type=event.target_type,
            target_id=event.target_id,
        )
        for event in await db.scalars(statement)
    ]
