"""Warnings for existing bindings affected by an open change set."""

from typing import cast
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import binding_rules, schemas
from ontology_platform.modules.ontology.models import ChangeSet, Element
from support import csrf_headers
from test_ontology_bindings_support import bind, bindings, change, save, steel
from test_ontology_support import add_ontology, change_set_items, sign_in
from test_route_protection import token_holder


async def _impacts(
    client: AsyncClient, ontology_id: object, change_set_id: str
) -> list[dict[str, str]]:
    response = await client.get(
        f"/api/ontologies/{ontology_id}/change-sets/{change_set_id}/binding-impacts"
    )
    assert response.status_code == 200, response.text
    return cast(list[dict[str, str]], response.json()["items"])


async def test_changed_property_domain_warns_for_existing_binding(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    weight = next(e for e in await bindings(db, s.ontology) if e.subject_id == s.weight.id)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, domainRef=str(s.cast.id))], apply=False
    )
    assert proposal.status_code == 200, proposal.text

    items = await _impacts(client, s.ontology.id, proposal.json()["changeSetId"])

    assert items == [
        {
            "elementId": str(weight.id),
            "kind": "property_binding",
            "label": "重量 → mes.heat.weight_t",
            "code": "binding.invalid",
            "message": "the property belongs to neither the bound type nor its parents",
        }
    ]


async def test_targeted_binding_is_not_reported(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    weight = next(e for e in await bindings(db, s.ontology) if e.subject_id == s.weight.id)
    proposal = await save(
        client,
        s.ontology,
        [
            change("update", s.weight, domainRef=str(s.heat.id)),
            change("update", weight, binding={"target": "column", "column": "weight_t"}),
        ],
        apply=False,
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    domain = next(
        item
        for item in await change_set_items(client, change_set_id)
        if item["targetElementId"] == str(s.weight.id)
    )
    response = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{domain['id']}",
        json={"edited": {"domainRef": str(s.cast.id)}},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert await _impacts(client, s.ontology.id, change_set_id) == []


async def test_rejected_target_still_excludes_existing_binding(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    weight = next(e for e in await bindings(db, s.ontology) if e.subject_id == s.weight.id)
    proposal = await save(
        client,
        s.ontology,
        [
            change("update", s.weight, domainRef=str(s.heat.id)),
            change("update", weight, binding={"target": "column", "column": "weight_t"}),
        ],
        apply=False,
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    domain = next(
        item
        for item in await change_set_items(client, change_set_id)
        if item["targetElementId"] == str(s.weight.id)
    )
    response = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{domain['id']}",
        json={"edited": {"domainRef": str(s.cast.id)}},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert await _impacts(client, s.ontology.id, change_set_id) == []
    target = next(
        item
        for item in await change_set_items(client, change_set_id)
        if item["targetElementId"] == str(weight.id)
    )
    response = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{target['id']}",
        json={"decision": "rejected"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert await _impacts(client, s.ontology.id, change_set_id) == []


async def test_relation_and_property_impacts_are_sorted_by_label(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    proposal = await save(
        client,
        s.ontology,
        [
            change("update", s.weight, domainRef=str(s.cast.id)),
            change("update", s.in_cast, domainRef=str(s.cast.id)),
        ],
        apply=False,
    )
    assert proposal.status_code == 200, proposal.text
    items = await _impacts(client, s.ontology.id, proposal.json()["changeSetId"])
    assert [(item["label"], item["kind"]) for item in items] == [
        ("对应浇次 → mes.heat.cast_no", "relation_binding"),
        ("重量 → mes.heat.weight_t", "property_binding"),
    ]


async def test_other_ontology_cannot_read_change_set_impacts(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    other = await add_ontology(db, key="other")
    await sign_in(client, db, Role.ADMIN)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, labelZh="新重量")], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    response = await client.get(
        f"/api/ontologies/{other.id}/change-sets/{change_set_id}/binding-impacts"
    )
    missing = await client.get(f"/api/change-sets/{UUID(int=0)}")
    assert response.status_code == missing.status_code == 404
    assert response.json()["code"] == missing.json()["code"] == "changeset.not_found"


async def test_targeted_binding_is_excluded_even_if_its_new_fields_fail(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    elements = [
        s.batch,
        s.heat,
        s.cast,
        s.weight,
        s.external_id,
        s.cast_no,
        s.batch_code,
        s.remark,
        s.in_cast,
        *await bindings(db, s.ontology),
    ]
    weight = next(
        e for e in elements if e.kind == "property_binding" and e.subject_id == s.weight.id
    )
    items = [
        binding_rules.Proposed(
            "update",
            "property",
            s.weight.id,
            None,
            schemas.ElementFields.model_validate({"domainRef": str(s.cast.id)}),
        ),
        binding_rules.Proposed(
            "update",
            "property_binding",
            weight.id,
            None,
            schemas.ElementFields.model_validate(
                {"binding": {"target": "column", "column": "heat_no"}}
            ),
        ),
    ]
    assert binding_rules.binding_impacts(elements, items) == []


async def test_rejected_items_do_not_contribute(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, domainRef=str(s.cast.id))], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    [item] = await change_set_items(client, change_set_id)
    response = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item['id']}",
        json={"decision": "rejected"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert await _impacts(client, s.ontology.id, change_set_id) == []


async def test_reviewer_edit_overrides_proposed_fields(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, domainRef=str(s.cast.id))], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    assert len(await _impacts(client, s.ontology.id, change_set_id)) == 1
    [item] = await change_set_items(client, change_set_id)
    response = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item['id']}",
        json={"edited": {"domainRef": str(s.heat.id)}},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert await _impacts(client, s.ontology.id, change_set_id) == []


async def test_closed_change_set_has_no_impacts(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, domainRef=str(s.cast.id))], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    assert len(await _impacts(client, s.ontology.id, change_set_id)) == 1
    for status in ("merged", "rejected"):
        await db.execute(
            update(ChangeSet).where(ChangeSet.id == UUID(change_set_id)).values(status=status)
        )
        await db.commit()
        assert await _impacts(client, s.ontology.id, change_set_id) == []


async def test_binding_already_invalid_is_not_reported(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    await db.execute(update(Element).where(Element.id == s.weight.id).values(domain_id=s.cast.id))
    await db.commit()
    proposal = await save(
        client, s.ontology, [change("update", s.cast, labelZh="新浇次")], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    assert await _impacts(client, s.ontology.id, proposal.json()["changeSetId"]) == []


async def test_ontology_without_bindings_has_no_impacts(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, domainRef=str(s.cast.id))], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    assert await _impacts(client, s.ontology.id, proposal.json()["changeSetId"]) == []


async def test_access_token_gets_same_error_as_change_set_detail(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    proposal = await save(
        client, s.ontology, [change("update", s.weight, labelZh="新重量")], apply=False
    )
    assert proposal.status_code == 200, proposal.text
    change_set_id = proposal.json()["changeSetId"]
    headers = await token_holder(client)
    detail = await client.get(f"/api/change-sets/{change_set_id}", headers=headers)
    impacts = await client.get(
        f"/api/ontologies/{s.ontology.id}/change-sets/{change_set_id}/binding-impacts",
        headers=headers,
    )
    assert detail.status_code == impacts.status_code == 403
    assert detail.json()["code"] == impacts.json()["code"] == "auth.token_not_allowed"
