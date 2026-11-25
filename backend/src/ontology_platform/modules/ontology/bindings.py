"""Read-only views of data bindings for other modules (spec 003, 6.6).

The M3 skeleton implements `table_usage`, which main.py and worker.py register as the
connectors module's usage provider (connectors must not import ontology). The binding view,
`bound_model` and `released_ontology` (and their data classes) arrive with batch 4a.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.service import TableUsage
from ontology_platform.modules.ontology import rules
from ontology_platform.modules.ontology.models import Element, Ontology, Release


def _label(row: dict[str, Any]) -> str:
    return rules.display_label(row.get("labelZh"), row.get("labelEn"), row.get("localName"))


async def table_usage(db: AsyncSession, data_source_id: UUID) -> list[TableUsage]:
    """Object types bound to tables of the data source, in working versions or in the release
    each ontology has in effect, by schema, table and type."""
    source = str(data_source_id)
    found: dict[tuple[str, str, UUID], dict[str, Any]] = {}

    bound = await db.execute(
        select(Element.subject_id, Element.binding).where(
            Element.kind == "type_binding",
            Element.status == "active",
            Element.binding["dataSourceId"].astext == source,
        )
    )
    working = [(subject_id, binding) for subject_id, binding in bound if subject_id and binding]
    labels: dict[UUID, str] = {}
    if working:
        subjects = await db.scalars(
            select(Element).where(Element.id.in_({subject_id for subject_id, _ in working}))
        )
        labels = {
            element.id: rules.display_label(element.label_zh, element.label_en, element.local_name)
            for element in subjects
        }
    for subject_id, binding in working:
        key = (str(binding["schema"]), str(binding["table"]), subject_id)
        entry = found.setdefault(key, {"label": labels.get(subject_id, ""), "working": False})
        entry["working"] = True

    snapshots = await db.scalars(
        select(Release.snapshot)
        .join(Ontology, Ontology.active_release_id == Release.id)
        .where(
            Release.snapshot.contains(
                [{"kind": "type_binding", "binding": {"dataSourceId": source}}]
            )
        )
    )
    for snapshot in snapshots:
        by_id = {str(row["id"]): row for row in snapshot}
        for row in snapshot:
            binding = row.get("binding") or {}
            if row.get("kind") != "type_binding" or binding.get("dataSourceId") != source:
                continue
            subject = by_id.get(str(row.get("subjectId")))
            subject_id = UUID(str(row["subjectId"]))
            key = (str(binding["schema"]), str(binding["table"]), subject_id)
            entry = found.setdefault(
                key, {"label": _label(subject) if subject else "", "working": False}
            )
            entry["released"] = True

    return [
        TableUsage(
            schema=schema,
            table=table,
            type_id=type_id,
            type_label=entry["label"],
            in_working_version=bool(entry.get("working")),
            in_active_release=bool(entry.get("released")),
        )
        for (schema, table, type_id), entry in sorted(found.items(), key=lambda item: item[0][:2])
    ]
