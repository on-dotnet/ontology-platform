"""`binding_proposals.propose_bindings`: how AI binding suggestions enter the ontology (spec 003,
section 8). Only as an open `ai_binding` change set waiting for review; what fails the binding
rules is left out with its reason, together with what depends on it."""

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import binding_proposals
from ontology_platform.modules.ontology import bindings as ontology_bindings
from ontology_platform.modules.ontology.binding_proposals import (
    DEPENDENCY_DROPPED,
    NotABindingProposalError,
)
from ontology_platform.modules.ontology.models import ChangeSet, Element
from ontology_platform.modules.ontology.schemas import (
    CatalogEvidenceSource,
    ElementFields,
    EvidenceIn,
    ProposedItem,
    ProposedMatch,
)
from test_ontology_bindings_support import (
    Steel,
    admin_id,
    bindings,
    foreign_key,
    steel,
    table,
)
from test_ontology_support import change_set_items, publish, sign_in


def _item(
    kind: str,
    fields: dict[str, Any],
    *,
    temp_ref: str | None = None,
    flags: list[str] | None = None,
    evidence: list[EvidenceIn] | None = None,
) -> ProposedItem:
    return ProposedItem.model_validate(
        {
            "op": "create",
            "kind": kind,
            "tempRef": temp_ref,
            "proposed": ElementFields.model_validate(fields),
            "confidence": 0.8,
            "rationale": "表注释写明了炉次。",
            "flags": flags or [],
            "evidence": evidence or [],
        }
    )


def _type(s: Steel, ref: str, subject: Element, name: str, keys: list[str]) -> ProposedItem:
    return _item(
        "type_binding",
        {"subjectRef": str(subject.id), "binding": table(s.mes, name, keys)},
        temp_ref=ref,
    )


def _column(subject: Element, parent: str, column: str) -> ProposedItem:
    return _item(
        "property_binding",
        {
            "subjectRef": str(subject.id),
            "parentRef": parent,
            "binding": {"target": "column", "column": column},
        },
    )


def _relation(s: Steel, domain: str, range_: str) -> ProposedItem:
    return _item(
        "relation_binding",
        {
            "subjectRef": str(s.in_cast.id),
            "domainRef": domain,
            "rangeRef": range_,
            "binding": foreign_key(),
        },
    )


async def _propose(db: AsyncSession, s: Steel, items: list[ProposedItem]) -> Any:
    proposal = await binding_proposals.propose_bindings(
        db, s.ontology.id, items=items, created_by=await admin_id(db), title="AI 绑定建议：MES"
    )
    await db.commit()
    return proposal


async def _change_sets(db: AsyncSession, s: Steel) -> int:
    count = await db.scalar(
        select(func.count()).select_from(ChangeSet).where(ChangeSet.ontology_id == s.ontology.id)
    )
    return int(count or 0)


def _codes(proposal: Any) -> list[tuple[int, str]]:
    return [(d.position, d.code) for d in proposal.dropped]


async def test_suggestions_become_one_open_ai_binding_change_set_waiting_for_review(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    assert (await publish(client, s.ontology)).status_code == 201
    released = await ontology_bindings.bound_model(db, s.ontology.id)
    elements = await db.scalar(
        select(func.count()).select_from(Element).where(Element.ontology_id == s.ontology.id)
    )
    source = CatalogEvidenceSource.model_validate(
        {"dataSourceId": str(s.mes.id), "schema": "mes", "table": "heat", "fact": "table"}
    )
    catalog = EvidenceIn(kind="catalog", source=source, quote="TABLE mes.heat")
    heat = _item(
        "type_binding",
        {"subjectRef": str(s.heat.id), "binding": table(s.mes)},
        temp_ref="new:table:1",
        flags=["key_unverified"],
        evidence=[catalog],
    )

    proposal = await _propose(db, s, [heat, _column(s.weight, "new:table:1", "weight_t")])

    assert (proposal.proposed, proposal.dropped) == (2, [])
    change_set = await db.get(ChangeSet, proposal.change_set_id)
    assert change_set is not None
    assert (change_set.source, change_set.status) == ("ai_binding", "open")
    items = await change_set_items(client, proposal.change_set_id)
    assert [i["decision"] for i in items] == ["pending", "pending"]
    assert items[0]["flags"] == ["key_unverified"]
    assert items[0]["confidence"] == 0.8
    assert [(e["kind"], e["quote"]) for e in items[0]["evidence"]] == [
        ("catalog", "TABLE mes.heat")
    ]
    # Nothing reached the working version or the release in effect.
    assert await bindings(db, s.ontology) == []
    assert (
        await db.scalar(
            select(func.count()).select_from(Element).where(Element.ontology_id == s.ontology.id)
        )
        == elements
    )
    assert await ontology_bindings.bound_model(db, s.ontology.id) == released


@pytest.mark.parametrize(
    "item",
    [
        ProposedItem(
            op="create",
            kind="entity_type",
            temp_ref="slab",
            proposed=ElementFields.model_validate({"localName": "Slab", "labelZh": "板坯"}),
        ),
        ProposedItem(
            op="create",
            kind="property",
            proposed=ElementFields.model_validate(
                {"localName": "width", "labelZh": "宽度", "datatype": "decimal"}
            ),
        ),
    ],
)
async def test_semantic_elements_are_refused(db: AsyncSession, item: ProposedItem) -> None:
    s = await steel(db)

    with pytest.raises(NotABindingProposalError):
        await _propose(db, s, [_type(s, "heat", s.heat, "heat", ["heat_no"]), item])

    assert await _change_sets(db, s) == 0


async def test_a_binding_with_an_alignment_is_refused(db: AsyncSession) -> None:
    s = await steel(db)
    item = _type(s, "heat", s.heat, "heat", ["heat_no"])
    item = item.model_copy(update={"match": ProposedMatch(kind="same", element_id=s.heat.id)})

    with pytest.raises(NotABindingProposalError):
        await _propose(db, s, [item])

    assert await _change_sets(db, s) == 0


async def test_only_new_bindings_are_taken(db: AsyncSession) -> None:
    s = await steel(db)
    update = ProposedItem(
        op="update",
        kind="type_binding",
        target_element_id=s.heat.id,
        proposed=ElementFields.model_validate({"binding": table(s.mes)}),
    )

    with pytest.raises(NotABindingProposalError):
        await _propose(db, s, [update])

    assert await _change_sets(db, s) == 0


async def test_failing_items_go_with_their_dependents_and_say_why(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    items = [
        _type(s, "heat", s.heat, "no_such_table", ["heat_no"]),
        _column(s.weight, "heat", "weight_t"),
        _type(s, "cast", s.cast, "cast", ["cast_no"]),
        _column(s.cast_no, "cast", "cast_no"),
        _relation(s, "heat", "cast"),
        _column(s.external_id, "cast", "no_such_column"),
    ]

    proposal = await _propose(db, s, items)

    assert _codes(proposal) == [
        (0, "binding.invalid"),
        (1, DEPENDENCY_DROPPED),
        (4, DEPENDENCY_DROPPED),
        (5, "binding.invalid"),
    ]
    assert all(d.message for d in proposal.dropped)
    assert proposal.proposed == 2
    kept = await change_set_items(client, proposal.change_set_id)
    assert [(i["kind"], i["decision"]) for i in kept] == [
        ("type_binding", "pending"),
        ("property_binding", "pending"),
    ]
    assert await bindings(db, s.ontology) == []


async def test_a_repeated_temp_ref_drops_the_later_item_only(db: AsyncSession) -> None:
    s = await steel(db)
    items = [
        _type(s, "heat", s.heat, "heat", ["heat_no"]),
        _type(s, "heat", s.cast, "cast", ["cast_no"]),
        _column(s.weight, "heat", "weight_t"),
    ]

    proposal = await _propose(db, s, items)

    assert _codes(proposal) == [(1, "binding.invalid")]
    assert proposal.proposed == 2


async def test_of_two_suggestions_for_the_same_property_the_later_goes(
    db: AsyncSession,
) -> None:
    s = await steel(db)
    items = [
        _type(s, "cast", s.cast, "cast", ["cast_no"]),
        _column(s.cast_no, "cast", "cast_no"),
        _column(s.cast_no, "cast", "cast_no"),
    ]

    proposal = await _propose(db, s, items)

    assert _codes(proposal) == [(2, "binding.duplicate")]
    assert proposal.proposed == 2


async def test_nothing_left_makes_no_change_set(db: AsyncSession) -> None:
    s = await steel(db)
    items = [
        _type(s, "heat", s.heat, "no_such_table", ["heat_no"]),
        _column(s.weight, "ghost", "weight_t"),
    ]

    proposal = await _propose(db, s, items)

    assert proposal.change_set_id is None
    assert proposal.proposed == 0
    assert sorted(_codes(proposal)) == [(0, "binding.invalid"), (1, "binding.invalid")]
    assert await _change_sets(db, s) == 0
    assert await bindings(db, s.ontology) == []


async def test_an_unknown_ontology_is_not_found(db: AsyncSession) -> None:
    s = await steel(db)

    with pytest.raises(AppError) as raised:
        await binding_proposals.propose_bindings(
            db,
            UUID(int=1),
            items=[_type(s, "heat", s.heat, "heat", ["heat_no"])],
            created_by=await admin_id(db),
            title="AI 绑定建议",
        )

    assert raised.value.code == "ontology.not_found"


# ---------- several candidates for one place ----------


def _candidates(s: Steel) -> list[ProposedItem]:
    return [
        _type(s, "t1", s.heat, "no_such_table", ["heat_no"]),
        _type(s, "t2", s.heat, "heat", ["heat_no"]),
        _type(s, "t3", s.heat, "heat_v", ["heat_no"]),
        _column(s.remark, "t2", "note"),  # jsonb: refused by the rules
        _column(s.remark, "t2", "remark"),
        _column(s.remark, "t2", "batch"),
        _column(s.weight, "t1", "weight_t"),  # under the table that failed
    ]


async def test_the_first_candidate_that_passes_takes_the_place(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)

    proposal = await _propose(db, s, _candidates(s))

    assert _codes(proposal) == [
        (0, "binding.invalid"),
        (2, "binding.duplicate"),
        (3, "binding.type_mismatch"),
        (5, "binding.duplicate"),
        (6, DEPENDENCY_DROPPED),
    ]
    kept = await change_set_items(client, proposal.change_set_id)
    assert [
        (i["kind"], i["proposed"]["binding"].get("table", i["proposed"]["binding"].get("column")))
        for i in kept
    ] == [
        ("type_binding", "heat"),
        ("property_binding", "remark"),
    ]


async def test_candidates_under_a_table_never_tried_go_as_its_dependents(
    db: AsyncSession,
) -> None:
    s = await steel(db)
    items = [
        _type(s, "t1", s.heat, "heat", ["heat_no"]),
        _type(s, "t2", s.heat, "heat_v", ["heat_no"]),
        _column(s.weight, "t2", "weight_t"),
        _column(s.weight, "t2", "weight_t"),
    ]

    proposal = await _propose(db, s, items)

    assert _codes(proposal) == [
        (1, "binding.duplicate"),
        (2, DEPENDENCY_DROPPED),
        (3, DEPENDENCY_DROPPED),
    ]
    assert proposal.proposed == 1


async def test_a_repeated_temp_ref_leaves_the_waiting_candidate_its_turn(
    db: AsyncSession,
) -> None:
    s = await steel(db)
    items = [
        _type(s, "t1", s.heat, "no_such_table", ["heat_no"]),
        _type(s, "t2", s.heat, "heat", ["heat_no"]),
        _type(s, "t2", s.cast, "cast", ["cast_no"]),  # repeats the ref of a waiting candidate
        _column(s.weight, "t2", "weight_t"),
    ]

    proposal = await _propose(db, s, items)

    assert _codes(proposal) == [(0, "binding.invalid"), (2, "binding.invalid")]
    assert proposal.proposed == 2


async def test_first_passing_makes_the_same_choice_and_writes_nothing(db: AsyncSession) -> None:
    s = await steel(db)
    events = await db.scalar(select(func.count()).select_from(AuditEvent))

    chosen = await binding_proposals.first_passing(db, s.ontology.id, _candidates(s))
    await db.commit()

    assert await _change_sets(db, s) == 0
    assert await db.scalar(select(func.count()).select_from(AuditEvent)) == events
    assert await bindings(db, s.ontology, active=False) == []
    proposal = await _propose(db, s, _candidates(s))
    assert chosen.taken == [1, 4]
    assert [(d.position, d.code) for d in chosen.dropped] == _codes(proposal)
    assert proposal.proposed == len(chosen.taken)
