"""The Protégé round-trip check behind `./dev.ps1 owl-check` (spec 002, 4.3).

    python -m ontology_platform.modules.ontology.owlcheck export <cases> <out>
    python -m ontology_platform.modules.ontology.owlcheck compare <cases> <saved> <owlapi.log>

`export` imports every case as a new ontology would and writes the platform's export to
<out>/<case>.ttl. OWL API (dev/owlapi) then loads and saves each export the way Protégé does.
`compare` reads OWL API's copies back as an import into that ontology. A case passes when the
copy changes nothing, or when only axioms the import flagged non_standard come back rewritten;
OWL API must also have parsed every triple. Cases: owl-features/*.ttl one by one, the steel
case's three files together, and extra/*.ttl (such as the dev stack's current releases).
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rdflib.namespace import DCTERMS

from ontology_platform.modules.ontology.rdf import reader, writer
from ontology_platform.modules.ontology.rdf.diff import Change, diff, keep_lost_lists
from ontology_platform.modules.ontology.rdf.reader import RdfInputError

# The export's dcterms:created; the comparison absorbs it as an import into the same ontology
# would.
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
STEEL = ("ontology", "shapes", "vocabulary")


def cases(root: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for path in sorted((root / "owl-features").glob("*.ttl")):
        found[path.stem] = path.read_bytes()
    steel = [root / "steel" / f"{name}.ttl" for name in STEEL]
    if all(path.exists() for path in steel):
        found["steel"] = b"\n".join(path.read_bytes() for path in steel)
    for path in sorted((root / "extra").glob("*.ttl")):
        found[f"extra-{path.stem}"] = path.read_bytes()
    return found


def _imported(data: bytes) -> tuple[reader.ReadResult, dict[str, str]]:
    result = reader.read(reader.parse_document(data))
    base = result.base_iri or "urn:x-owl-check:"
    if result.file_ontology_iri is None:
        result.state.ontology_iri = writer.ontology_iri_of(base)
    return result, writer.prefix_map("checked", base, result.prefixes)


def export_case(data: bytes) -> str:
    result, prefixes = _imported(data)
    return writer.export(result.state, prefixes, version=None, created=CREATED)


@dataclass(frozen=True, slots=True)
class Outcome:
    case: str
    # same: nothing changed; rewritten: only flagged axioms changed; changed / error: failed.
    status: str
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status in ("same", "rewritten")


def _describe(change: Change) -> str:
    if change.element is not None:
        return f"{change.op} {change.kind} {change.element.iri}"
    if change.axiom is not None:
        return f"{change.op} axiom about {change.axiom.subject or 'a blank node'}"
    return change.op


def compare_case(case: str, original: bytes, saved: bytes) -> Outcome:
    first, _ = _imported(original)
    try:
        copy = reader.read(
            reader.parse_document(saved),
            ontology_iri=first.state.ontology_iri,
            absorb={DCTERMS.created: writer.created_literal(CREATED)},
        )
    except RdfInputError as error:
        return Outcome(case, "error", f"the saved copy cannot be read: {error.detail}")
    kept = keep_lost_lists(first.state, copy.state)
    note = f"{kept} sh:in lists dropped by OWL API, values kept" if kept else ""
    changes = diff(first.state, copy.state).changes
    if not changes:
        return Outcome(case, "same", note)
    deleted = [change for change in changes if change.op == "delete"]
    if deleted and all(c.axiom is not None and c.axiom.non_standard for c in deleted):
        return Outcome(case, "rewritten", f"{len(deleted)} non-standard axioms rewritten")
    shown = "; ".join(_describe(change) for change in changes[:5])
    more = f" (and {len(changes) - 5} more)" if len(changes) > 5 else ""
    return Outcome(case, "changed", f"{len(changes)} changes: {shown}{more}")


def _owlapi_results(log: Path) -> dict[str, tuple[str, int, str]]:
    found: dict[str, tuple[str, int, str]] = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 5 and parts[0] == "RESULT":
            found[Path(parts[1]).stem] = (parts[2], int(parts[3]), parts[4])
    return found


def compare(root: Path, saved: Path, log: Path) -> list[Outcome]:
    results = _owlapi_results(log)
    outcomes: list[Outcome] = []
    for case, data in cases(root).items():
        status, unparsed, message = results.get(case, ("missing", 0, "OWL API did not run"))
        if status != "ok":
            outcomes.append(Outcome(case, "error", f"OWL API: {message}"))
        elif unparsed:
            outcomes.append(Outcome(case, "error", f"OWL API left {unparsed} triples unparsed"))
        else:
            copy = saved / f"{case}.ttl"
            outcomes.append(compare_case(case, data, copy.read_bytes()))
    return outcomes


def main(argv: Sequence[str]) -> int:
    if len(argv) == 3 and argv[0] == "export":
        root, out = Path(argv[1]), Path(argv[2])
        out.mkdir(parents=True, exist_ok=True)
        for case, data in cases(root).items():
            (out / f"{case}.ttl").write_text(export_case(data), encoding="utf-8")
            print(f"exported {case}")
        return 0
    if len(argv) == 4 and argv[0] == "compare":
        outcomes = compare(Path(argv[1]), Path(argv[2]), Path(argv[3]))
        for outcome in outcomes:
            print(f"{outcome.status:<9} {outcome.case}  {outcome.detail}".rstrip())
        failed = [outcome for outcome in outcomes if not outcome.passed]
        print(f"{len(outcomes) - len(failed)} of {len(outcomes)} cases pass")
        return 1 if failed else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
