"""R2RML downloads from published bindings (spec 003, section 10)."""

from uuid import uuid4

from httpx import AsyncClient
from pydantic import SecretStr
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.term import Node
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.secrets import seal
from ontology_platform.modules.identity.models import Role
from ontology_platform.settings import Settings
from test_mcp_support import new_token
from test_ontology_bindings_support import (
    _table,
    bind,
    bindings,
    change,
    foreign_key,
    link_table,
    property_binding,
    relation_binding,
    save,
    steel,
    table,
    type_binding,
)
from test_ontology_support import add_elements, element, publish, sign_in
from test_query_support import assert_problem

RR = Namespace("http://www.w3.org/ns/r2rml#")


def _object_map(graph: Graph, triples_map: Node, predicate: URIRef) -> Node:
    [obj] = [
        obj
        for pom in graph.objects(triples_map, RR.predicateObjectMap)
        if (pom, RR.predicate, predicate) in graph
        for obj in graph.objects(pom, RR.objectMap)
    ]
    return obj


def _joins(graph: Graph, obj: Node) -> set[tuple[str, str]]:
    pairs = set()
    for condition in graph.objects(obj, RR.joinCondition):
        [child] = graph.objects(condition, RR.child)
        [parent] = graph.objects(condition, RR.parent)
        pairs.add((str(child), str(parent)))
    return pairs


def _value(graph: Graph, node: Node, first: URIRef, second: URIRef) -> Node:
    [middle] = graph.objects(node, first)
    [value] = graph.objects(middle, second)
    return value


async def test_download_maps_every_binding(
    client: AsyncClient, db: AsyncSession, settings: Settings
) -> None:
    s = await steel(db)
    password = "r2rml-fixture-password"
    encrypted = seal(settings, s.mes.id, SecretStr(password))
    s.mes.secret, s.mes.secret_key_id = encrypted.secret, encrypted.key_id
    base = s.ontology.base_iri
    cast_iri = "https://vocab.example/Casting"
    s.cast.iri = cast_iri
    s.cast_no.iri = "https://vocab.example/number"
    s.in_cast.iri = "https://vocab.example/inCasting"
    key = r'key{"}\part'
    view = _table(
        s.mes, r'cast"view\1', [(key, "text", "string"), ("seq", "integer", "integer")], kind="view"
    )
    view.schema_name = "Plant.A"
    link = _table(s.mes, "members", [(c, "text", "string") for c in ("h", "s", "k")])
    db.add_all([view, link])
    reverse = element(
        s.ontology, "relation_type", "hasHeat", "Has heat", domain_id=s.cast.id, range_id=s.heat.id
    )
    member = element(
        s.ontology,
        "relation_type",
        "memberOf",
        "Member of",
        domain_id=s.heat.id,
        range_id=s.cast.id,
    )
    await add_elements(db, reverse, member)
    cast_table = table(s.mes, view.table_name, ["seq", key])
    cast_table["schema"] = view.schema_name
    fk = foreign_key(["cast_no", "batch"], [key, "seq"])
    reverse_fk = foreign_key(["cast_no", "batch"], [key, "seq"], side="target")
    membership = link_table(["h"], ["s", "k"])
    membership["join"]["table"] = link.table_name
    await sign_in(client, db, Role.ADMIN)
    edits = await save(
        client,
        s.ontology,
        [
            type_binding(s.heat, table(s.mes), "heat"),
            type_binding(s.cast, cast_table, "cast"),
            property_binding(s.cast_no, "cast", key),
            relation_binding(s.in_cast, "heat", "cast", fk),
            relation_binding(reverse, "cast", "heat", reverse_fk),
            relation_binding(member, "heat", "cast", membership),
        ],
    )
    assert edits.status_code == 200, edits.text
    released = await publish(client, s.ontology)
    assert released.status_code == 201, released.text
    assert released.json()["bindingCount"] == 6
    url = f"/api/releases/{released.json()['id']}/r2rml"
    await sign_in(client, db, Role.EDITOR)
    response = await client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/turtle; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="steel-v1-r2rml.ttl"'
    assert response.content == (await client.get(url)).content
    private_values = (
        s.mes.host,
        s.mes.username,
        s.mes.database,
        f":{s.mes.port}/",
        password,
        str(s.mes.id),
    )
    for private in private_values:
        assert private not in response.text

    graph = Graph().parse(data=response.content, format="turtle")
    maps = list(graph.subjects(RDF.type, RR.TriplesMap))
    assert len(maps) == 3
    by_table = {str(_value(graph, tm, RR.logicalTable, RR.tableName)): tm for tm in maps}
    heat = by_table['"mes"."heat"']
    cast = by_table[r'"Plant.A"."cast""view\1"']
    members = by_table['"mes"."members"']
    assert _value(graph, heat, RR.subjectMap, RR["class"]) == URIRef(base + "Heat")
    assert _value(graph, cast, RR.subjectMap, RR["class"]) == URIRef(cast_iri)
    assert _value(graph, heat, RR.subjectMap, RR.template) == Literal(base + 'Heat/{"heat_no"}')
    assert _value(graph, cast, RR.subjectMap, RR.template) == Literal(
        cast_iri + r'/{"seq"}/{"key\{""\}\\part"}'
    )
    prop = _object_map(graph, cast, URIRef(s.cast_no.iri))
    assert list(graph.objects(prop, RR.column)) == [Literal(r'"key{""}\part"')]
    forward = _object_map(graph, heat, URIRef(s.in_cast.iri))
    backward = _object_map(graph, cast, URIRef(base + "hasHeat"))
    assert list(graph.objects(forward, RR.parentTriplesMap)) == [cast]
    assert list(graph.objects(backward, RR.parentTriplesMap)) == [heat]
    pairs = {('"cast_no"', r'"key{""}\part"'), ('"batch"', '"seq"')}
    assert _joins(graph, forward) == pairs
    assert _joins(graph, backward) == {(parent, child) for child, parent in pairs}
    assert _value(graph, members, RR.subjectMap, RR.template) == Literal(base + 'Heat/{"h"}')
    target = _object_map(graph, members, URIRef(base + "memberOf"))
    assert list(graph.objects(target, RR.template)) == [Literal(cast_iri + '/{"s"}/{"k"}')]


async def test_export_reads_the_requested_snapshot(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    first = await publish(client, s.ontology)
    assert first.status_code == 201, first.text
    url = f"/api/releases/{first.json()['id']}/r2rml"
    before = await client.get(url)
    assert before.status_code == 200
    weight = next(row for row in await bindings(db, s.ontology) if row.subject_id == s.weight.id)
    edits = await save(client, s.ontology, [change("delete", weight)])
    assert edits.status_code == 200, edits.text
    assert edits.json()["merged"] is True
    assert (await client.get(url)).content == before.content
    second = await publish(client, s.ontology)
    assert second.status_code == 201, second.text
    latest = await client.get(f"/api/releases/{second.json()['id']}/r2rml")
    assert latest.status_code == 200
    assert "weight_t" in before.text
    assert "weight_t" not in latest.text
    assert (await client.get(url)).content == before.content


async def test_empty_release_and_missing_release(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.REVIEWER)
    released = await publish(client, s.ontology)
    assert released.status_code == 201, released.text
    response = await client.get(f"/api/releases/{released.json()['id']}/r2rml")
    assert response.status_code == 200
    assert response.text.strip() == "@prefix rr: <http://www.w3.org/ns/r2rml#> ."
    assert len(Graph().parse(data=response.content, format="turtle")) == 0
    assert_problem(await client.get(f"/api/releases/{uuid4()}/r2rml"), 404, "release.not_found")


async def test_export_requires_an_editor_session(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    token, _ = await new_token(client, db, Role.ADMIN, ["ontology:read", "objects:read"])
    released = await publish(client, s.ontology)
    assert released.status_code == 201, released.text
    url = f"/api/releases/{released.json()['id']}/r2rml"
    client.cookies.clear()
    assert_problem(await client.get(url), 401, "auth.not_authenticated")
    by_token = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert_problem(by_token, 403, "auth.token_not_allowed")
    await sign_in(client, db, Role.VIEWER)
    assert_problem(await client.get(url), 403, "auth.forbidden")
