"""The Protégé round-trip check (`./dev.ps1 owl-check`) without OWL API: its case list, its
verdicts on OWL API's recorded copies, and how it reads OWL API's log."""

import shutil
from pathlib import Path

import pytest

from ontology_platform.modules.ontology import owlcheck

FIXTURES = Path(__file__).parent / "fixtures" / "ontology"
SAMPLES = FIXTURES / "samples"
REWRITTEN = {"15-cardinality", "16-boolean", "21-advanced"}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    shutil.copytree(SAMPLES / "owl-features", tmp_path / "owl-features")
    shutil.copytree(SAMPLES / "steel", tmp_path / "steel")
    (tmp_path / "extra").mkdir()
    shutil.copy(FIXTURES / "platform-v1.ttl", tmp_path / "extra" / "steel-v1.ttl")
    return tmp_path


def test_cases_cover_the_samples_and_the_extras(root: Path) -> None:
    found = owlcheck.cases(root)

    assert len(found) == 21 + 2
    assert {"01-iri", "21-advanced", "steel", "extra-steel-v1"} <= set(found)


@pytest.mark.parametrize("path", sorted((SAMPLES / "owl-features").glob("*.ttl")), ids=str)
def test_verdicts_on_what_owl_api_saved(path: Path) -> None:
    saved = (FIXTURES / "owlapi" / path.name).read_bytes()

    outcome = owlcheck.compare_case(path.stem, path.read_bytes(), saved)

    assert outcome.status == ("rewritten" if path.stem in REWRITTEN else "same")
    assert outcome.passed


def test_compare_case_accepts_equivalent_owl_api_spellings() -> None:
    header = b"""
        @prefix ex: <urn:t:> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:A a owl:Class . ex:B a owl:Class . ex:p a owl:ObjectProperty .
    """
    original = b"""
        ex:p rdfs:domain [ a owl:Class ; owl:unionOf ( ex:A ex:B ) ] .
        ex:A owl:disjointWith ex:B .
    """
    saved = b"""
        ex:p rdfs:domain [ a owl:Class ; owl:unionOf ( ex:B ex:A ) ] .
        ex:B owl:disjointWith ex:A . xsd:date a rdfs:Datatype .
    """
    outcome = owlcheck.compare_case("equivalence", header + original, header + saved)

    assert outcome.status == "same", outcome.detail
    assert outcome.passed


def test_a_real_change_fails() -> None:
    original = (SAMPLES / "owl-features" / "03-subclass.ttl").read_bytes()
    saved = b"@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:g3:C> a owl:Class ."

    outcome = owlcheck.compare_case("03-subclass", original, saved)

    assert outcome.status == "changed"
    assert not outcome.passed


def test_export_then_compare(root: Path, tmp_path: Path) -> None:
    out = tmp_path / "export"
    assert owlcheck.main(["export", str(root), str(out)]) == 0
    saved = tmp_path / "saved"
    shutil.copytree(out, saved)
    lines = [f"RESULT\t{path.name}\tok\t0\tfine" for path in sorted(out.glob("*.ttl"))]
    lines[0] = lines[0].replace("\tok\t0\t", "\tok\t2\t")
    log = tmp_path / "owlapi.log"
    log.write_text("\n".join(lines), encoding="utf-8")

    outcomes = owlcheck.compare(root, saved, log)

    assert [o.status for o in outcomes].count("error") == 1
    assert all(o.status == "same" for o in outcomes[1:])


def test_an_unrelated_change_in_a_rewritten_case_fails() -> None:
    original = (SAMPLES / "owl-features" / "21-advanced.ttl").read_bytes()
    saved = (FIXTURES / "owlapi" / "21-advanced.ttl").read_bytes()
    # ex:q is not part of the rewritten class constructors.
    extra = b'\n<urn:synthetic:m5:q> <http://www.w3.org/2000/01/rdf-schema#label> "Q"@en .\n'

    assert owlcheck.compare_case("21-advanced", original, saved).status == "rewritten"
    assert owlcheck.compare_case("21-advanced", original, saved + extra).status == "changed"


def test_a_changed_kind_fails() -> None:
    original = b"@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:t:A> a owl:Class ."
    saved = b"@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:t:A> a owl:ObjectProperty ."

    assert owlcheck.compare_case("kind", original, saved).status == "changed"
