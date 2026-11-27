"""The steel ontology bundle (spec 006, overall acceptance) survives a platform round trip.

fixtures/steel-ontology/steel.ttl is a copy of ontologies/steel/dist/steel.ttl (the test image only
contains backend/); copy it again and update DIGEST whenever check.ps1 -Build changes dist.
"""

from hashlib import sha256
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from test_ontology_import import export, lost, upload
from test_ontology_support import change_set_items, decide, merge, sign_in

BUNDLE = Path(__file__).parent / "fixtures" / "steel-ontology" / "steel.ttl"
DIST = Path(__file__).resolve().parents[2] / "ontologies" / "steel" / "dist" / "steel.ttl"
DIGEST = "1f303b49e022933699f6323353ac7dc53967154541ae2bc6c0fa781578f925c9"
# The decisions endpoint takes at most 5000 items per request.
BATCH = 5000


def test_fixture_matches_dist() -> None:
    content = BUNDLE.read_bytes()
    # Only a repository checkout has dist; the test image checks the digest alone.
    if DIST.is_file():
        assert DIST.read_bytes() == content
    assert sha256(content).hexdigest() == DIGEST


async def test_bundle_round_trip(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = BUNDLE.read_bytes()

    response = await upload(client, source, filename="steel.ttl")
    assert response.status_code == 201, response.text
    result = response.json()
    # Classes with two named parents, and SHACL-SPARQL or other shapes the form editor does not
    # cover, are kept as axioms; the import says so.
    assert {w["code"] for w in result["warnings"]} <= {"multiple_parents", "unsupported_shape"}
    change_set_id = result["changeSetId"]
    ids = [item["id"] for item in await change_set_items(client, change_set_id)]
    assert ids
    for start in range(0, len(ids), BATCH):
        decided = await decide(client, change_set_id, ids[start : start + BATCH], "accepted")
        assert decided.status_code == 200, decided.text
    merged = await merge(client, change_set_id)
    assert merged.status_code == 200, merged.text
    assert merged.json()["skipped"] == []

    ontology_id = result["ontology"]["id"]
    exported = await export(client, ontology_id)
    assert lost(source, exported) == []

    again = await upload(client, exported.encode(), ontology_id=ontology_id, filename="steel.ttl")
    assert again.status_code == 200, again.text
    assert again.json()["changeSetId"] is None
    assert again.json()["counts"] == {"create": 0, "update": 0, "delete": 0, "restore": 0}
