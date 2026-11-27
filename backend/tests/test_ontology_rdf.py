"""RDF import and export without the database (spec 002, sections 3 to 5).

fixtures/ontology/samples holds copies of samples/owl-features and of the steel case files (the
test image only contains backend/); keep them identical to samples/. fixtures/ontology/owlapi
holds what OWL API 4.5.29, the library inside Protégé 5, wrote back for each original file
(recorded 2026-11-23); platform-v1.ttl is the M1 walkthrough's published v1.
"""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pyshacl import validate
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from ontology_platform.modules.ontology.owlcheck import explained_by_rewrites
from ontology_platform.modules.ontology.rdf import axioms, reader, writer
from ontology_platform.modules.ontology.rdf.declarations import implied_declarations
from ontology_platform.modules.ontology.rdf.diff import diff, keep_lost_lists
from ontology_platform.modules.ontology.rdf.model import (
    ElementState,
    OntologyState,
    Triple,
    canonical_key,
)
from ontology_platform.modules.ontology.rdf.reader import RdfInputError, parse_document, read
from ontology_platform.modules.ontology.rdf.vocab import DECLARATION_TYPES, SH

FIXTURES = Path(__file__).parent / "fixtures" / "ontology"
SAMPLES = FIXTURES / "samples"
OWL_FEATURES = sorted((SAMPLES / "owl-features").glob("*.ttl"))
STEEL_FILES = [SAMPLES / "steel" / f"{name}.ttl" for name in ("ontology", "shapes", "vocabulary")]
PLATFORM_V1 = FIXTURES / "platform-v1.ttl"
CREATED = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)
# OWL API rewrites these (spec 002, 4.3): the cardinality typed xsd:integer and the named
# classes with a class constructor.
REWRITTEN = {"15-cardinality.ttl", "16-boolean.ttl", "21-advanced.ttl"}

CASES = {path.name: [path] for path in [*OWL_FEATURES, *STEEL_FILES, PLATFORM_V1]}
CASES["steel"] = STEEL_FILES
INVERSE_PAIR = FIXTURES / "inverse-pair.ttl"
CASES[INVERSE_PAIR.name] = [INVERSE_PAIR]


def load(paths: list[Path]) -> Graph:
    return parse_document(b"\n".join(path.read_bytes() for path in paths))


def export(result: reader.ReadResult) -> str:
    prefixes = writer.prefix_map("sample", result.base_iri or "urn:x:", result.prefixes)
    return writer.export(result.state, prefixes, version=None, created=CREATED)


def parse(text: str) -> Graph:
    return parse_document(text.encode())


def has_blank(triple: Triple) -> bool:
    return isinstance(triple[0], BNode) or isinstance(triple[2], BNode)


def exact_key(triples: list[Triple]) -> str:
    return canonical_key(triples, exact=True)


def missing_from(source: Graph, output: Graph) -> list[str]:
    """Triples of `source` not in `output`, blank node structures compared up to renaming and
    literals compared exactly as written."""
    missing = [
        " ".join(term.n3() for term in triple)
        for triple in source
        if not has_blank(triple) and triple not in output
    ]
    available = Counter(exact_key(g) for g in axioms.group(t for t in output if has_blank(t)))
    for component in axioms.group(t for t in source if has_blank(t)):
        key = exact_key(component)
        if available[key] > 0:
            available[key] -= 1
        else:
            missing.append(key)
    return missing


# ---------- round trip ----------


@pytest.mark.parametrize("case", sorted(CASES))
def test_import_then_export_keeps_every_triple(case: str) -> None:
    source = load(CASES[case])

    output = parse(export(read(source)))

    assert missing_from(source, output) == []


@pytest.mark.parametrize("case", sorted(CASES))
def test_exporting_again_changes_nothing(case: str) -> None:
    first = read(load(CASES[case]))
    text = export(first)

    again = read(
        parse(text),
        ontology_iri=first.state.ontology_iri,
        absorb={DCTERMS.created: writer.created_literal(CREATED)},
    )

    assert list(diff(first.state, again.state).changes) == []
    assert export(again) == text


def test_literal_spelling_is_kept() -> None:
    source = load([SAMPLES / "owl-features" / "21-advanced.ttl"])

    output = parse(export(read(source)))

    lexicals = {str(o) for o in output.objects() if isinstance(o, Literal)}
    assert {"+02", "001"} <= lexicals


def test_imports_are_kept_but_not_loaded() -> None:
    result = read(load([SAMPLES / "owl-features" / "18-imports.ttl"]))

    output = parse(export(result))

    assert (URIRef("urn:g3:o"), OWL.imports, URIRef("http://192.0.2.1/must-not-fetch")) in output


@pytest.mark.parametrize("name", [path.name for path in OWL_FEATURES])
def test_what_protege_saves_reads_back_the_same(name: str) -> None:
    original = read(load([SAMPLES / "owl-features" / name]))
    saved = read(load([FIXTURES / "owlapi" / name]), ontology_iri=original.state.ontology_iri)

    result = diff(original.state, saved.state)

    if name in REWRITTEN:
        # Only the flagged axioms are replaced, touching nothing else they do not mention.
        assert result.changes
        assert explained_by_rewrites(result)
    else:
        assert result.changes == []
        assert result.kind_changed == []


def protege_pair(name: str) -> tuple[reader.ReadResult, reader.ReadResult]:
    source = PLATFORM_V1 if name == "platform-v1.ttl" else SAMPLES / "steel" / name[6:]
    original = read(load([source]))
    saved = read(load([FIXTURES / "owlapi" / name]), ontology_iri=original.state.ontology_iri)
    return original, saved


@pytest.mark.parametrize("name", ["platform-v1.ttl", "steel-ontology.ttl", "steel-vocabulary.ttl"])
def test_protege_copies_of_the_steel_files_read_back_the_same(name: str) -> None:
    original, saved = protege_pair(name)

    assert diff(original.state, saved.state).changes == []


def test_protege_drops_sh_in_lists() -> None:
    # Read on its own the file's shapes stay axioms; OWL API leaves `sh:in [ ]` in them.
    original, saved = protege_pair("steel-shapes.ttl")

    changes = diff(original.state, saved.state).changes

    assert changes
    assert all(
        change.axiom is not None and any(p == SH["in"] for _, p, _ in change.axiom.triples)
        for change in changes
    )


def test_protege_copy_of_the_steel_case_keeps_the_platform_lists() -> None:
    original = read(load(STEEL_FILES))
    copies = [FIXTURES / "owlapi" / f"steel-{path.name}" for path in STEEL_FILES]
    saved = read(load(copies), ontology_iri=original.state.ontology_iri)

    assert saved.warnings["lost_list"] == 5
    assert keep_lost_lists(original.state, saved.state) == 5
    assert diff(original.state, saved.state).changes == []


@pytest.mark.parametrize("name", [path.name for path in OWL_FEATURES])
def test_declarations_match_owl_api(name: str) -> None:
    if name in REWRITTEN:
        pytest.skip("OWL API rewrites this file instead of only declaring")
    source = load([SAMPLES / "owl-features" / name])
    saved = load([FIXTURES / "owlapi" / name])

    added_by_owlapi = {
        (s, p, o)
        for s, p, o in saved
        if p == RDF.type
        and o in DECLARATION_TYPES
        and isinstance(s, URIRef)
        and (s, p, o) not in source
    }
    ours = {t for t in implied_declarations(source) if t not in source}

    assert ours == added_by_owlapi


def test_steel_constraints_validate_the_sample_data() -> None:
    result = read(load(STEEL_FILES))
    shapes = parse(export(result))
    constraints = [e for e in result.state.elements.values() if e.kind == "constraint"]

    good = Graph().parse(SAMPLES / "steel" / "data.ttl")
    bad = Graph().parse(SAMPLES / "steel" / "invalid-data.ttl")

    assert len(constraints) == 5
    assert validate(good, shacl_graph=shapes)[0] is True
    assert validate(bad, shacl_graph=shapes)[0] is False


# ---------- mapping rules ----------

PREFIXES = """\
@prefix ex: <urn:t:> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix op: <https://w3id.org/ontology-platform/vocab#> .
"""


def read_text(body: str) -> reader.ReadResult:
    return read(parse(PREFIXES + body))


def test_elements_take_labels_references_and_units() -> None:
    result = read_text(
        """
        ex:Slab a owl:Class ; rdfs:label "板坯"@zh, "Slab"@en, "另一个"@zh ;
            skos:definition "连铸产出。"@zh ; skos:altLabel "铸坯"@zh, "Cast slab"@en ;
            rdfs:subClassOf ex:Product .
        ex:Product a owl:Class .
        ex:width a owl:DatatypeProperty ; rdfs:domain ex:Slab ; rdfs:range xsd:decimal ;
            op:unit "mm" .
        ex:of a owl:ObjectProperty ; rdfs:domain ex:Slab ; rdfs:range ex:Product ;
            owl:inverseOf ex:has .
        ex:has a owl:ObjectProperty .
        """,
    )
    elements = result.state.elements

    slab = elements["urn:t:Slab"]
    assert (slab.kind, slab.label_zh, slab.label_en, slab.parent) == (
        "entity_type",
        "另一个",  # the first by spelling; the other Chinese label stays an axiom
        "Slab",
        "urn:t:Product",
    )
    assert set(slab.synonyms) == {("zh", "铸坯"), ("en", "Cast slab")}
    width = elements["urn:t:width"]
    assert (width.domain, width.datatype, width.unit) == ("urn:t:Slab", "decimal", "mm")
    assert (width.required, width.multiple, width.auto_shape) == (False, True, False)
    assert elements["urn:t:of"].inverse == "urn:t:has"
    kept = [
        a
        for a in result.state.axioms
        if (URIRef("urn:t:Slab"), RDFS.label, Literal("板坯", lang="zh")) in a.triples
    ]
    assert len(kept) == 1


def test_what_does_not_fit_stays_an_axiom() -> None:
    result = read_text(
        """
        ex:A a owl:Class ; rdfs:subClassOf ex:B, ex:C .
        ex:B a owl:Class . ex:C a owl:Class .
        ex:p a owl:DatatypeProperty ; rdfs:domain ex:A, ex:B ; rdfs:range xsd:float .
        ex:x a owl:Class, owl:ObjectProperty .
        ex:A rdfs:label " 带空格"@zh .
        """,
    )
    a = result.state.elements["urn:t:A"]
    p = result.state.elements["urn:t:p"]

    assert a.parent is None
    assert a.label_zh is None
    assert p.domain is None
    assert p.datatype is None
    assert "urn:t:x" not in result.state.elements
    assert result.warnings["multiple_parents"] == 1
    kept = {(str(s), str(pr)) for axiom in result.state.axioms for s, pr, _ in axiom.triples}
    assert ("urn:t:A", str(RDFS.subClassOf)) in kept
    assert ("urn:t:p", str(RDFS.range)) in kept
    assert ("urn:t:x", str(RDF.type)) in kept


def test_a_parent_loop_is_left_as_axioms() -> None:
    result = read_text(
        "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:A .",
    )
    elements = result.state.elements

    assert (elements["urn:t:A"].parent, elements["urn:t:B"].parent) == (None, "urn:t:A")
    (kept,) = result.state.axioms
    assert kept.triples == ((URIRef("urn:t:A"), RDFS.subClassOf, URIRef("urn:t:B")),)


def test_platform_shapes_become_required_and_multiple() -> None:
    result = read_text(
        """
        ex:Coil a owl:Class .
        ex:weight a owl:DatatypeProperty ; rdfs:domain ex:Coil ; rdfs:range xsd:decimal .
        ex:tag a owl:DatatypeProperty ; rdfs:domain ex:Coil ; rdfs:range xsd:string .
        <urn:t:Coil-shape> a sh:NodeShape ; sh:targetClass ex:Coil ;
            sh:property [ sh:path ex:weight ; sh:datatype xsd:decimal ;
                          sh:minCount 1 ; sh:maxCount 1 ] ,
                        [ sh:path ex:tag ; sh:datatype xsd:string ] .
        """,
    )
    elements = result.state.elements

    assert elements["urn:t:Coil"].auto_shape is True
    weight, tag = elements["urn:t:weight"], elements["urn:t:tag"]
    assert (weight.auto_shape, weight.required, weight.multiple) == (True, True, False)
    assert (tag.auto_shape, tag.required, tag.multiple) == (True, False, True)
    assert result.state.axioms == []


def test_other_shapes_become_constraints_or_axioms() -> None:
    result = read_text(
        """
        ex:Coil a owl:Class .
        ex:weight a owl:DatatypeProperty .
        ex:CoilShape a sh:NodeShape ; sh:targetClass ex:Coil ; rdfs:label "钢卷规则"@zh ;
            sh:property [ sh:path ex:weight ; sh:minInclusive 0 ; sh:maxInclusive 100 ;
                          sh:in ( 1 2 ) ; sh:message "重量不对"@zh ] .
        ex:OddShape a sh:NodeShape ; sh:targetClass ex:Coil ; sh:closed true .
        """,
    )
    shape = result.state.elements["urn:t:CoilShape"]

    assert (shape.kind, shape.domain, shape.label_zh) == ("constraint", "urn:t:Coil", "钢卷规则")
    (rule,) = shape.rules
    assert rule.path == "urn:t:weight"
    assert rule.min_inclusive == Literal("0", datatype=XSD.integer)
    assert rule.in_ == (Literal("1", datatype=XSD.integer), Literal("2", datatype=XSD.integer))
    assert rule.message == (Literal("重量不对", lang="zh"),)
    assert "urn:t:OddShape" not in result.state.elements
    assert result.warnings["unsupported_shape"] == 1


def test_non_standard_axioms_are_flagged() -> None:
    result = read_text(
        """
        ex:A a owl:Class . ex:B a owl:Class .
        ex:Or owl:unionOf ( ex:A ex:B ) .
        ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:minCardinality 1 ] .
        ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;
            owl:maxCardinality "2"^^xsd:nonNegativeInteger ] .
        """,
    )
    flagged = sorted(axiom.non_standard for axiom in result.state.axioms if len(axiom.triples) > 1)

    assert flagged == [False, True, True]
    assert result.warnings["non_standard"] == 2


def test_shared_blank_nodes_are_copied_per_use() -> None:
    graph = parse(
        PREFIXES + "ex:a ex:p _:list . ex:b ex:p _:list . _:list rdf:first 1 ; rdf:rest rdf:nil .",
    )

    result = read(graph)

    assert len(result.state.axioms) == 2
    assert len({axiom.key for axiom in result.state.axioms}) == 2


def test_import_into_an_ontology_renames_the_header_and_absorbs_generated_values() -> None:
    stamp = Literal("2026-11-23T08:00:00+00:00", datatype=XSD.dateTime)
    graph = parse(
        PREFIXES
        + '<urn:t:file> a owl:Ontology ; rdfs:label "名称" ; owl:versionIRI <urn:t:file/1> ;'
        ' <http://purl.org/dc/terms/created> "2026-11-23T08:00:00+00:00"^^xsd:dateTime .',
    )

    result = read(
        graph,
        ontology_iri="urn:t:mine",
        absorb={URIRef("http://purl.org/dc/terms/created"): stamp},
    )

    assert result.state.name == "名称"
    assert result.file_ontology_iri == "urn:t:file"
    (axiom,) = result.state.axioms
    assert axiom.triples == ((URIRef("urn:t:mine"), OWL.versionIRI, URIRef("urn:t:file/1")),)


# ---------- writer ----------


def test_writer_uses_lists_labels_and_roots() -> None:
    graph = Graph()
    a, b, shared = URIRef("urn:t:a"), URIRef("urn:t:b"), BNode()
    graph.add((a, RDFS.seeAlso, shared))
    graph.add((b, RDFS.seeAlso, shared))
    graph.add((shared, RDFS.label, Literal("x")))
    root = BNode()
    graph.add((root, RDF.type, OWL.AllDisjointClasses))
    head, rest = BNode(), BNode()
    graph.add((root, OWL.members, head))
    graph.add((head, RDF.first, a))
    graph.add((head, RDF.rest, rest))
    graph.add((rest, RDF.first, b))
    graph.add((rest, RDF.rest, RDF.nil))

    prefixes = {"t": "urn:t:", "owl": str(OWL), "rdfs": str(RDFS)}

    text = writer.TurtleWriter(graph, prefixes).fragment()

    assert "owl:members ( t:a t:b )" in text
    assert "_:b0" in text
    header = "".join(f"@prefix {name}: <{iri}> .\n" for name, iri in prefixes.items())
    assert len(Graph().parse(data=header + text, format="turtle")) == len(graph)


def test_working_export_declares_what_it_uses() -> None:
    result = read_text("ex:i a ex:Thing .")

    output = parse(export(result))

    assert (URIRef("urn:t:i"), RDF.type, OWL.NamedIndividual) in output
    assert (URIRef("urn:t:Thing"), RDF.type, OWL.Class) in output
    assert (SH.path, RDF.type, OWL.AnnotationProperty) not in output


# ---------- input checks ----------


def test_input_limits_and_errors() -> None:
    with pytest.raises(RdfInputError) as too_large:
        parse_document(b"#" * (reader.MAX_BYTES + 1))
    with pytest.raises(RdfInputError) as owl_xml:
        parse_document(b'<?xml version="1.0"?><Ontology xmlns="http://www.w3.org/2002/07/owl#"/>')
    with pytest.raises(RdfInputError) as broken:
        parse_document(b"@prefix ex: <urn:t:> .\nex:a ex:p ex:b ;\n ex:q .")
    with pytest.raises(RdfInputError) as empty:
        parse_document(b"# nothing here\n")
    with pytest.raises(RdfInputError) as entity:
        parse_document(
            b'<?xml version="1.0"?><!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>',
        )
    with pytest.raises(RdfInputError) as binary:
        parse_document(b"\xff\xfe\x00\x01")

    assert too_large.value.code == "import.too_large"
    assert owl_xml.value.code == "import.unsupported_format"
    assert (broken.value.code, broken.value.line) == ("import.parse_error", 3)
    assert empty.value.code == "import.empty"
    assert entity.value.code == "import.unsupported_format"
    assert binary.value.code == "import.unsupported_format"


def test_too_many_triples() -> None:
    body = "".join(f"<urn:t:s{i}> <urn:t:p> {i} .\n" for i in range(reader.MAX_TRIPLES + 1))

    with pytest.raises(RdfInputError) as error:
        parse_document(body.encode())

    assert error.value.code == "import.too_many_triples"


def test_rdf_xml_is_read() -> None:
    graph = parse_document(
        b'<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
        b' xmlns:owl="http://www.w3.org/2002/07/owl#">'
        b'<owl:Class rdf:about="urn:t:A"/></rdf:RDF>',
    )

    assert read(graph).state.elements["urn:t:A"].kind == "entity_type"


# ---------- diff ----------


def test_diff_lists_each_kind_of_change() -> None:
    before = read_text(
        """
        ex:A a owl:Class ; rdfs:label "甲"@zh .
        ex:B a owl:Class .
        ex:A rdfs:comment "说明" .
        ex:n ex:v "01"^^xsd:integer .
        """,
    ).state
    after = read_text(
        """
        ex:A a owl:Class ; rdfs:label "甲类"@zh .
        ex:C a owl:Class .
        ex:n ex:v "1"^^xsd:integer .
        """,
    ).state
    before.elements["urn:t:C"] = ElementState(
        kind="entity_type",
        iri="urn:t:C",
        active=False,
        multiple=True,
    )

    changes = {
        (c.op, c.kind, c.element.iri if c.element else None) for c in diff(before, after).changes
    }

    assert changes == {
        ("update", "entity_type", "urn:t:A"),
        ("restore", "entity_type", "urn:t:C"),
        ("delete", "entity_type", "urn:t:B"),
        ("delete", "axiom", None),
    }


def axiom_state(body: str) -> OntologyState:
    return OntologyState("urn:t:ontology", axioms=axioms.axioms_of(parse(PREFIXES + body)))


@pytest.mark.parametrize(
    "predicate",
    [
        "unionOf",
        "intersectionOf",
        "oneOf",
        "disjointUnionOf",
        "members",
        "distinctMembers",
        "hasKey",
    ],
)
def test_diff_compares_owl_set_members_with_multiplicity(predicate: str) -> None:
    def state(members: str) -> OntologyState:
        return axiom_state(f"ex:S owl:{predicate} ( {members} ) .")

    original = state("ex:A ex:A ex:B")
    assert diff(original, state("ex:B ex:A ex:A")).changes == []
    for changed in (state("ex:A ex:A ex:C"), state("ex:A ex:B")):
        assert [c.op for c in diff(original, changed).changes] == ["create", "delete"]


def test_diff_compares_literal_enumerations_by_value() -> None:
    original = axiom_state('ex:T owl:oneOf ( "01"^^xsd:integer "blue" ) .')
    reordered = axiom_state('ex:T owl:oneOf ( "blue" "1"^^xsd:integer ) .')
    assert diff(original, reordered).changes == []


def test_diff_compares_restriction_members_by_structure() -> None:
    restriction = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ]"
    original = axiom_state(f"ex:S owl:intersectionOf ( ex:A {restriction} ) .")
    reordered = f"ex:S owl:intersectionOf ( {restriction} ex:A ) ."
    assert diff(original, axiom_state(reordered)).changes == []
    changed = axiom_state(reordered.replace("ex:B", "ex:C"))
    assert [c.op for c in diff(original, changed).changes] == ["create", "delete"]


def test_diff_compares_nested_set_lists() -> None:
    original = axiom_state("ex:S owl:unionOf ( ex:A [ owl:intersectionOf ( ex:B ex:C ) ] ) .")
    reordered = axiom_state("ex:S owl:unionOf ( [ owl:intersectionOf ( ex:C ex:B ) ] ex:A ) .")
    assert diff(original, reordered).changes == []


@pytest.mark.parametrize("predicate", ["owl:propertyChainAxiom", "owl:withRestrictions", "sh:in"])
def test_diff_keeps_other_lists_in_order(predicate: str) -> None:
    body = f"ex:S owl:unionOf ( [ {predicate} ( ex:A ex:B ) ] ex:C ) ."
    changed = body.replace("ex:A ex:B", "ex:B ex:A")
    assert [c.op for c in diff(axiom_state(body), axiom_state(changed)).changes] == [
        "create",
        "delete",
    ]


@pytest.mark.parametrize(
    "defect",
    [
        "_:tail rdf:rest rdf:nil ; rdf:first ex:extra .",
        "",
        "_:tail rdf:rest _:head .",
        "_:tail rdf:rest rdf:nil . ex:other ex:ref _:tail .",
    ],
    ids=["two-firsts", "missing-rest", "cycle", "shared-tail"],
)
def test_diff_preserves_malformed_lists(defect: str) -> None:
    def state(first: str, second: str) -> OntologyState:
        return axiom_state(
            f"ex:S owl:unionOf _:head . _:head rdf:first {first} ; rdf:rest _:tail . "
            f"_:tail rdf:first {second} . {defect}"
        )

    original = state("ex:A", "ex:B")
    assert diff(original, state("ex:A", "ex:B")).changes == []
    assert [c.op for c in diff(original, state("ex:B", "ex:A")).changes] == ["create", "delete"]


@pytest.mark.parametrize(
    "predicate",
    [
        "disjointWith",
        "equivalentClass",
        "equivalentProperty",
        "propertyDisjointWith",
        "sameAs",
        "differentFrom",
    ],
)
def test_diff_ignores_direction_between_symmetric_iris(predicate: str) -> None:
    original = axiom_state(f"ex:A owl:{predicate} ex:B .")
    reversed_pair = axiom_state(f"ex:B owl:{predicate} ex:A .")
    assert diff(original, reversed_pair).changes == []


def test_diff_keeps_direction_for_an_anonymous_equivalent_class() -> None:
    restriction = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ]"
    original = axiom_state(f"ex:A owl:equivalentClass {restriction} .")
    reversed_pair = axiom_state(f"{restriction} owl:equivalentClass ex:A .")
    assert [c.op for c in diff(original, reversed_pair).changes] == ["create", "delete"]


def test_diff_skips_only_xsd_datatype_declarations() -> None:
    empty = OntologyState("urn:t:ontology")
    declared = axiom_state("xsd:date a rdfs:Datatype . xsd:gYear a rdfs:Datatype .")
    assert len(declared.axioms) == 2
    assert diff(empty, declared).changes == []
    assert diff(declared, empty).changes == []

    custom = axiom_state("ex:MyType a rdfs:Datatype .")
    (change,) = diff(empty, custom).changes
    assert (change.op, change.axiom) == ("create", custom.axioms[0])


# ---------- found in review ----------


@pytest.mark.parametrize(
    "body",
    [
        "ex:a ex:p _:x . _:x ex:q _:x .",
        "ex:a ex:p _:x . _:x ex:q _:y . _:y ex:r _:x .",
        "ex:a ex:p _:x . ex:b ex:p _:x . _:x ex:q _:y . _:y ex:r _:x .",
    ],
    ids=["self-loop", "two-cycle", "shared-cycle"],
)
def test_blank_node_cycles_survive(body: str) -> None:
    source = parse(PREFIXES + body)

    first = read(source)
    output = parse(export(first))

    assert missing_from(source, output) == []
    assert export(read(output)) == export(first)


def test_long_lists_need_no_recursion() -> None:
    members = " ".join(f"ex:i{n}" for n in range(1500))
    values = " ".join(str(n) for n in range(1000))
    source = parse(
        PREFIXES
        + f"ex:Big a owl:Class ; owl:oneOf ( {members} ) .\n"
        + "ex:C a owl:Class . ex:v a owl:DatatypeProperty .\n"
        + "ex:S a sh:NodeShape ; sh:targetClass ex:C ;\n"
        + f"    sh:property [ sh:path ex:v ; sh:in ( {values} ) ] .",
    )

    result = read(source)
    output = parse(export(result))

    assert missing_from(source, output) == []
    (rule,) = result.state.elements["urn:t:S"].rules
    assert rule.in_ is not None
    assert len(rule.in_) == 1000


def test_what_the_api_cannot_hold_stays_an_axiom() -> None:
    synonyms = ", ".join(f'"别名{n}"@zh' for n in range(101))
    result = read_text(
        f"ex:A a owl:Class ; skos:altLabel {synonyms} .\n"
        "ex:v a owl:DatatypeProperty .\n"
        "ex:S a sh:NodeShape ; sh:targetClass ex:A ;\n"
        '    sh:property [ sh:path ex:v ; sh:message ""@zh ] .',
    )

    assert len(result.state.elements["urn:t:A"].synonyms) == 100
    assert "urn:t:S" not in result.state.elements
    assert result.warnings["unsupported_shape"] == 1
    kept = [t for a in result.state.axioms for t in a.triples if t[1] == SKOS.altLabel]
    assert len(kept) == 1


def test_header_values_are_absorbed_only_when_they_match() -> None:
    body = '<urn:t:file> a owl:Ontology ; rdfs:label "文件里的名称" ; dcterms:description "说明" .'
    graph = parse(PREFIXES + "@prefix dcterms: <http://purl.org/dc/terms/> .\n" + body)

    adopted = read(graph)
    strict = read(
        graph, ontology_iri="urn:t:mine", known=reader.KnownHeader("平台名称", "说明", strict=True)
    )
    named = read(graph, known=reader.KnownHeader(name="用户给的名称"))

    assert (adopted.state.name, adopted.state.description) == ("文件里的名称", "说明")
    assert (strict.state.name, strict.state.description) == (None, "说明")
    (label,) = strict.state.axioms
    assert label.triples == ((URIRef("urn:t:mine"), RDFS.label, Literal("文件里的名称")),)
    assert (named.state.name, named.state.description) == (None, "说明")


def test_an_anonymous_header_belongs_to_the_ontology() -> None:
    graph = parse(
        PREFIXES + '[] a owl:Ontology ; rdfs:comment "无名本体的说明" . ex:A a owl:Class .'
    )

    result = read(graph, ontology_iri="urn:t:mine")
    output = parse(export(result))

    (comment,) = result.state.axioms
    assert comment.triples == ((URIRef("urn:t:mine"), RDFS.comment, Literal("无名本体的说明")),)
    assert len(list(output.subjects(RDF.type, OWL.Ontology))) == 1


def test_inverses_in_both_directions() -> None:
    result = read_text(
        "ex:p a owl:ObjectProperty ; owl:inverseOf ex:q .\n"
        "ex:q a owl:ObjectProperty ; owl:inverseOf ex:p .",
    )

    elements = result.state.elements
    assert (elements["urn:t:p"].inverse, elements["urn:t:q"].inverse) == ("urn:t:q", "urn:t:p")
    assert result.state.axioms == []


def test_tree_keys_match_rdflib_canonical_keys() -> None:
    # The fast key for blank node trees and rdflib's general canonicalization agree on what is
    # equal; a cycle falls back to rdflib.
    first = parse(PREFIXES + "ex:a ex:p [ ex:q ( 1 2 ) ; ex:r [ ex:s 3 ] ] .")
    same = parse(PREFIXES + "ex:a ex:p [ ex:r [ ex:s 3 ] ; ex:q ( 1 2 ) ] .")
    other = parse(PREFIXES + "ex:a ex:p [ ex:q ( 2 1 ) ; ex:r [ ex:s 3 ] ] .")
    ring = PREFIXES + "ex:a ex:p _:x . _:x ex:q _:y . _:y ex:r _:x ."

    assert canonical_key(list(first)) == canonical_key(list(same))
    assert canonical_key(list(first)) != canonical_key(list(other))
    assert canonical_key(list(parse(ring))) == canonical_key(list(parse(ring)))


def test_protege_keeps_one_direction_of_an_inverse_pair() -> None:
    # OWL API writes `p owl:inverseOf q` once for a pair that names each other; the other
    # direction is implied, so the copy compares equal.
    original = read(load([INVERSE_PAIR]))
    saved = read(
        load([FIXTURES / "owlapi" / INVERSE_PAIR.name]), ontology_iri=original.state.ontology_iri
    )

    assert original.state.elements["urn:g3:q"].inverse == "urn:g3:p"
    assert saved.state.elements["urn:g3:q"].inverse is None
    assert diff(original.state, saved.state).changes == []
