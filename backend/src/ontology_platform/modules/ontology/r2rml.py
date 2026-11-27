"""Export the bindings in a release snapshot as an R2RML mapping graph."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology.models import Ontology, Release
from ontology_platform.modules.ontology.rdf.writer import TurtleWriter
from ontology_platform.modules.ontology.schemas import JoinBinding, LinkTableJoin

RR = Namespace("http://www.w3.org/ns/r2rml#")
_TEMPLATE_ESCAPES = str.maketrans({"\\": "\\\\", "{": "\\{", "}": "\\}"})


def _identifier(name: str) -> str:
    # Catalog names are exact, including case and embedded double quotes.
    return '"' + name.replace('"', '""') + '"'


def _template(class_iri: URIRef, columns: Sequence[str]) -> Literal:
    keys = ["{" + _identifier(column).translate(_TEMPLATE_ESCAPES) + "}" for column in columns]
    return Literal("/".join([class_iri.translate(_TEMPLATE_ESCAPES), *keys]))


def _map_iri(binding_id: str) -> URIRef:
    return URIRef(f"urn:uuid:{binding_id}")


def _triples_map(graph: Graph, node: URIRef, schema: str, table: str, template: Literal) -> BNode:
    logical_table, subject = BNode(), BNode()
    name = ".".join(_identifier(part) for part in (schema, table) if part)
    graph.add((node, RDF.type, RR.TriplesMap))
    graph.add((node, RR.logicalTable, logical_table))
    graph.add((logical_table, RR.tableName, Literal(name)))
    graph.add((node, RR.subjectMap, subject))
    graph.add((subject, RR.template, template))
    return subject


def _object_map(graph: Graph, node: URIRef, predicate: URIRef) -> BNode:
    pom, obj = BNode(), BNode()
    graph.add((node, RR.predicateObjectMap, pom))
    graph.add((pom, RR.predicate, predicate))
    graph.add((pom, RR.objectMap, obj))
    return obj


def export_r2rml(snapshot: Sequence[Mapping[str, Any]]) -> str:
    """Serialize only the published IRIs and the tables, columns and joins bound to them."""
    # The lookups below never miss on a published snapshot: publishing runs
    # binding_rules.node_problems, which requires every binding's subject and both ends of a
    # relation binding to be active. Loosening those rules must revisit this function.
    iris = {row["id"]: URIRef(row["iri"]) for row in snapshot if row.get("iri")}
    datatypes = {
        row["id"]: row.get("datatype") for row in snapshot if row["kind"] == "property"
    }
    classes = {
        row["id"]: iris[row["subjectId"]] for row in snapshot if row["kind"] == "type_binding"
    }
    graph = Graph(bind_namespaces="none")
    for row in snapshot:
        kind = row["kind"]
        if kind == "type_binding":
            table = row["binding"]
            class_iri = classes[row["id"]]
            subject = _triples_map(
                graph,
                _map_iri(row["id"]),
                table["schema"],
                table["table"],
                _template(class_iri, table["keyColumns"]),
            )
            graph.add((subject, RR["class"], class_iri))
        elif kind == "property_binding":
            obj = _object_map(graph, _map_iri(row["parentId"]), iris[row["subjectId"]])
            graph.add((obj, RR.column, Literal(_identifier(row["binding"]["column"]))))
            datatype = datatypes[row["subjectId"]]
            if datatype:
                graph.add((obj, RR.datatype, XSD[datatype]))
        elif kind == "relation_binding":
            source, target = row["domainId"], row["rangeId"]
            predicate = iris[row["subjectId"]]
            join = JoinBinding.model_validate(row["binding"]).join
            if isinstance(join, LinkTableJoin):
                link = _map_iri(row["id"])
                _triples_map(
                    graph,
                    link,
                    join.schema_name,
                    join.table,
                    _template(classes[source], join.source_columns),
                )
                obj = _object_map(graph, link, predicate)
                graph.add((obj, RR.template, _template(classes[target], join.target_columns)))
            else:
                obj = _object_map(graph, _map_iri(source), predicate)
                graph.add((obj, RR.parentTriplesMap, _map_iri(target)))
                # The R2RML child always supplies the RDF subject, even for an incoming FK.
                children, parents = join.columns, join.references
                if join.side == "target":
                    children, parents = parents, children
                for child, parent in zip(children, parents, strict=True):
                    condition = BNode()
                    graph.add((obj, RR.joinCondition, condition))
                    graph.add((condition, RR.child, Literal(_identifier(child))))
                    graph.add((condition, RR.parent, Literal(_identifier(parent))))

    writer = TurtleWriter(graph, {"rr": str(RR), "xsd": str(XSD)})
    return f"@prefix rr: <{RR}> .\n@prefix xsd: <{XSD}> .\n\n{writer.fragment()}\n"


async def export_release(db: AsyncSession, release_id: UUID) -> tuple[str, str]:
    row = (
        await db.execute(
            select(Release.snapshot, Release.version, Ontology.key)
            .join(Ontology, Ontology.id == Release.ontology_id)
            .where(Release.id == release_id)
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "release.not_found", "Release not found.")
    snapshot, version, key = row
    return await asyncio.to_thread(export_r2rml, snapshot), f"{key}-v{version}-r2rml.ttl"
