"""The workbench summary, composed from the other modules' services."""

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.documents import service as documents
from ontology_platform.modules.identity import service as identity
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.workbench.schemas import Activity, WorkbenchSummary

# Work on the ontology only; sign-ins are not news for the whole team and stay in the audit log.
ACTIVITY_PREFIXES = ("ontology.", "document.", "changeset.", "release.")
ACTIVITY_LIMIT = 10


async def summary(db: AsyncSession) -> WorkbenchSummary:
    events = await audit.recent(db, prefixes=ACTIVITY_PREFIXES, limit=ACTIVITY_LIMIT)
    names = await identity.display_names(db, {e.actor_id for e in events if e.actor_id})
    return WorkbenchSummary(
        pending_change_sets=await ontology.count_open_change_sets(db),
        entity_types=await ontology.count_entity_types(db),
        processing_documents=await documents.count_processing(db),
        recent_activity=[
            Activity(
                id=str(event.id),
                action=event.action,
                occurred_at=event.occurred_at,
                actor_name=names.get(event.actor_id) if event.actor_id else None,
                target_type=event.target_type,
                target_id=event.target_id,
            )
            for event in events
        ],
    )
