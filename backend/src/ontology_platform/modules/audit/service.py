"""Audit recording. Events join the caller's transaction and persist when it commits."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent


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


async def recent(db: AsyncSession, *, prefixes: Sequence[str], limit: int = 10) -> list[AuditEvent]:
    """The latest events whose action starts with one of `prefixes`, newest first."""
    statement = (
        select(AuditEvent)
        .where(or_(*(AuditEvent.action.startswith(prefix) for prefix in prefixes)))
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return list(await db.scalars(statement))
