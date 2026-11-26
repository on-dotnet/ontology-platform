from hashlib import sha256
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from test_ontology_import import export, import_and_merge, lost
from test_ontology_support import sign_in

FIXTURES = Path(__file__).parent / "fixtures" / "qa" / "steel"
ROOT = Path(__file__).resolve().parents[2]
EX = "urn:synthetic:metals:"
# The test image only contains backend/. Pin the sample bytes there as well.
SAMPLE_DIGESTS = {
    "ontology.ttl": "c5e0937068beedf04e479f6f3f4727db19d355efbdd0a689a4e9bf0fe836f15c",
    "expected-bindings.toml": "ea46aa16b485890603ae3162a015794bdfcfb4d80a714e27e8bd00975f855e89",
    "questions.toml": "709830a77531cf14d0019c738b0d1b1e77ec13e33bf6f83bb1ac2b60209bb608",
    "metrics.toml": "3d6a8e53b4b43ef65ad067357cd6fb835281b5c6b9f0546670e125de601fee36",
}


def test_demo_fixture_matches_samples() -> None:
    for name, digest in SAMPLE_DIGESTS.items():
        content = (FIXTURES / name).read_bytes()
        if (ROOT / "backend").is_dir():
            assert (ROOT / "samples" / "steel" / "qa" / name).read_bytes() == content, name
        assert sha256(content).hexdigest() == digest, name


async def test_demo_ontology_import(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = (FIXTURES / "ontology.ttl").read_bytes()
    assert "表面缺陷" not in source.decode("utf-8")
    result = await import_and_merge(client, source, filename="ontology.ttl")
    assert result["warnings"] == []
    ontology_id = result["ontology"]["id"]
    response = await client.get(f"/api/ontologies/{ontology_id}/elements")
    assert response.status_code == 200
    elements = {item["iri"]: item for item in response.json()}
    inspection = elements[EX + "QualityInspection"]
    assert (inspection["kind"], inspection["labelZh"]) == ("entity_type", "质量检验")
    for name, owner, datatype, label, unit in [
        ("steelGrade", "Heat", "string", "钢种", None),
        ("coilStatus", "Coil", "string", "状态", None),
        ("thickness", "Coil", "decimal", "厚度", "mm"),
        ("yieldStrength", "QualityInspection", "integer", "屈服强度", "MPa"),
        ("tensileStrength", "QualityInspection", "integer", "抗拉强度", "MPa"),
        ("elongation", "QualityInspection", "decimal", "断后伸长率", "%"),
        ("impactEnergy", "QualityInspection", "integer", "冲击功", "J"),
        ("passed", "QualityInspection", "boolean", "是否合格", None),
        ("inspectionDate", "QualityInspection", "date", "检验日期", None),
    ]:
        prop = elements[EX + name]
        assert prop["kind"] == "property"
        assert prop["domainId"] == elements[EX + owner]["id"]
        assert (prop["datatype"], prop["labelZh"], prop["unit"]) == (datatype, label, unit)
    relation = elements[EX + "inspects"]
    assert (relation["kind"], relation["labelZh"]) == ("relation_type", "检验对象")
    assert relation["domainId"] == inspection["id"]
    assert relation["rangeId"] == elements[EX + "Coil"]["id"]

    for shape, name, minimum, maximum, requirement in [
        ("YieldStrengthShape", "yieldStrength", "235", None, "ReH ≥ 235 MPa"),
        ("TensileStrengthShape", "tensileStrength", "370", "500", "370 ≤ Rm ≤ 500 MPa"),
        ("ElongationShape", "elongation", "26", None, "A ≥ 26%"),
        ("ImpactEnergyShape", "impactEnergy", "27", None, "KV2 ≥ 27 J"),
    ]:
        constraint = elements[EX + shape]
        assert (constraint["kind"], constraint["domainId"]) == ("constraint", inspection["id"])
        (rule,) = constraint["rules"]
        assert rule["pathId"] == elements[EX + name]["id"]
        assert rule["message"] == [{"lang": "zh", "text": f"资料 04 第 2 节：{requirement}。"}]
        for key, bound in [("minInclusive", minimum), ("maxInclusive", maximum)]:
            if bound is None:
                assert rule[key] is None
            else:
                assert (rule[key]["lexical"], rule[key]["datatype"]) == (bound, "integer")

    grade_shape = elements[EX + "SteelGradeShape"]
    assert grade_shape["kind"] == "constraint"
    assert grade_shape["domainId"] == elements[EX + "Heat"]["id"]
    (grade_rule,) = grade_shape["rules"]
    assert grade_rule["pathId"] == elements[EX + "steelGrade"]["id"]
    assert grade_rule["allowedValuesLost"] is False
    assert [(v["lexical"], v["datatype"], v["lang"]) for v in grade_rule["allowedValues"]] == [
        ("Q235B", None, None),
        ("Q275B", None, None),
    ]
    assert lost(source, await export(client, ontology_id)) == []
