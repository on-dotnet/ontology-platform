import asyncio
import tomllib
from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.cq import service
from ontology_platform.modules.cq.models import CompetencyQuestionRow
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.query.cursor import encode_key
from query_path_support import qa_steel_fixture  # noqa: F401
from support import csrf_headers
from test_ontology_support import add_ontology, sign_in
from test_qa_demo_import import FIXTURES
from test_query_paging import SteelObjects
from test_query_support import assert_problem


def question(text: str, expect: str = 'kind = "answerable"') -> bytes:
    return f'[[questions]]\ntext = "{text}"\n[questions.expect]\n{expect}\n'.encode()


async def upload(
    client: AsyncClient, url: str, content: bytes, *, multipart: bool = False
) -> Response:
    headers = csrf_headers(client)
    if multipart:
        return await client.post(
            url, files={"file": ("questions.toml", content, "text/plain")}, headers=headers
        )
    return await client.post(
        url, content=content, headers={**headers, "Content-Type": "text/plain; charset=utf-8"}
    )


@pytest.fixture
async def import_url(client: AsyncClient, db: AsyncSession) -> str:
    ontology = await add_ontology(db)
    await sign_in(client, db, Role.EDITOR)
    return f"/api/ontologies/{ontology.id}/competency-questions/import"


async def test_import_steel_questions(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects
) -> None:
    content = (FIXTURES / "questions.toml").read_bytes()
    url = f"/api/ontologies/{qa_steel.ontology.id}/competency-questions/import"
    response = await upload(client, url, content, multipart=True)
    assert response.status_code == 200, response.text
    assert response.json() == {"created": 5, "skipped": 0}
    statement = select(CompetencyQuestionRow).order_by(CompetencyQuestionRow.position)
    rows = (await db.scalars(statement)).all()
    questions = tomllib.loads(content.decode())["questions"]
    assert [(r.text, r.note) for r in rows] == [(q["text"], q["note"]) for q in questions]
    assert [r.expect_kind for r in rows] == [q["expect"]["kind"] for q in questions]
    for row, entry, type_name in zip(rows[:2], questions[:2], ["Heat", "Coil"], strict=True):
        assert row.expect_objects is not None
        assert row.expect_objects["typeId"] == qa_steel.ids[type_name]
        assert set(row.expect_objects["keys"]) == {encode_key([k]) for k in entry["expect"]["keys"]}
    assert rows[2].expect_number == Decimal("0.9230769230769231")
    assert rows[2].tolerance == Decimal("0.0005")
    assert (await upload(client, url, content)).json() == {"created": 0, "skipped": 5}


@pytest.mark.parametrize(
    ("expect", "field"),
    [
        ('kind = "objects"\ntypeIri = "urn:missing"\nkeys = ["A"]', "typeIri"),
        ('kind = "number"\nnumber = "1"\ntolerance = "-0.1"', "tolerance"),
        ('kind = "number"\nnumber = "not a number"', "number"),
        ('kind = "unknown"', "kind"),
    ],
)
async def test_invalid_question_rejects_whole_import(
    client: AsyncClient, import_url: str, expect: str, field: str
) -> None:
    assert (await upload(client, import_url, question("Saved"))).status_code == 200
    response = await upload(client, import_url, question("New") + question("Saved", expect))
    assert_problem(response, 422, "cq.invalid_import")
    assert "questions[2]" in response.json()["detail"]
    assert field in response.json()["detail"]
    items = (await client.get(import_url.removesuffix("/import"))).json()["items"]
    assert [item["text"] for item in items] == ["Saved"]


async def test_prepares_all_entries_once_before_appending(
    client: AsyncClient, import_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare = AsyncMock(wraps=service.prepare_question)
    append = AsyncMock(wraps=service.append_questions)
    monkeypatch.setattr(service, "prepare_question", prepare)
    monkeypatch.setattr(service, "append_questions", append)
    invalid = question("A", 'kind = "number"\nnumber = "1e131072"')
    response = await upload(client, import_url, question("A") + invalid)
    assert_problem(response, 422, "cq.invalid_import")
    assert "questions[2]" in response.json()["detail"]
    assert prepare.await_count == 2
    append.assert_not_awaited()

    prepare.reset_mock()
    response = await upload(client, import_url, question("A") * 2 + question("B"))
    assert response.json() == {"created": 2, "skipped": 1}
    assert prepare.await_count == 3
    append.assert_awaited_once()
    assert append.await_args is not None
    assert [row.text for row in append.await_args.args[2]] == ["A", "B"]


async def test_empty_import_checks_ontology(client: AsyncClient, import_url: str) -> None:
    response = await upload(client, import_url, b"questions = []")
    assert response.json() == {"created": 0, "skipped": 0}
    missing = f"/api/ontologies/{uuid4()}/competency-questions/import"
    for content in (b"", b"questions = []"):
        assert_problem(await upload(client, missing, content), 404, "ontology.not_found")


@pytest.mark.parametrize("field", ["text", "note"])
async def test_invalid_postgres_text_reports_item(
    client: AsyncClient, import_url: str, field: str
) -> None:
    invalid = b'[[questions]]\ntext = "A"\nnote = "B"\n[questions.expect]\nkind = "answerable"'
    invalid = invalid.replace(field.encode() + b' = "', field.encode() + b' = "\\u0000')
    response = await upload(client, import_url, question("First") + invalid)
    assert_problem(response, 422, "cq.invalid_import")
    detail = response.json()["detail"]
    assert "questions[2]" in detail
    assert field in detail


async def test_repeated_and_parallel_imports_skip_same_text(
    client: AsyncClient, import_url: str
) -> None:
    content = question("同一条") * 2
    results = await asyncio.gather(
        upload(client, import_url, content), upload(client, import_url, content)
    )
    assert [r.status_code for r in results] == [200, 200]
    assert sorted((r.json()["created"], r.json()["skipped"]) for r in results) == [(0, 2), (1, 1)]
    [item] = (await client.get(import_url.removesuffix("/import"))).json()["items"]
    archive = await client.post(
        f"/api/competency-questions/{item['id']}/archive", headers=csrf_headers(client)
    )
    assert archive.status_code == 200, archive.text
    assert (await upload(client, import_url, content)).json() == {"created": 0, "skipped": 2}


@pytest.mark.parametrize("multipart", [False, True])
async def test_import_file_size_and_length_limits(
    client: AsyncClient, import_url: str, multipart: bool
) -> None:
    questions = b"".join(question(str(i)) for i in range(50))
    content = questions.ljust(64 * 1024, b" ")
    for invalid in (content + b" ", questions + question("51"), b"[[questions]", b"\xff"):
        response = await upload(client, import_url, invalid, multipart=multipart)
        assert_problem(response, 422, "cq.invalid_import")
    response = await upload(client, import_url, content, multipart=multipart)
    assert response.status_code == 200, response.text
    assert response.json() == {"created": 50, "skipped": 0}


async def test_import_requires_a_single_multipart_file(
    client: AsyncClient, import_url: str
) -> None:
    file = ("questions.toml", question("A"), "text/plain")
    headers = csrf_headers(client)
    for files in ([("file", file), ("file", file)], [("unexpected", file)]):
        response = await client.post(import_url, files=files, headers=headers)
        assert_problem(response, 422, "cq.invalid_import")
    response = await client.post(import_url, json={"questions": []}, headers=headers)
    assert_problem(response, 422, "cq.invalid_import")


@pytest.mark.parametrize("multipart", [False, True])
async def test_oversize_stream_stops_reading(
    client: AsyncClient, import_url: str, multipart: bool
) -> None:
    async def stream() -> AsyncIterator[bytes]:
        if multipart:
            yield (
                b'--cq\r\nContent-Disposition: form-data; name="file"; '
                b'filename="questions.toml"\r\n\r\n'
            )
        for _ in range(2):
            yield b" " * 65536
        pytest.fail("The application kept reading an oversized request.")

    media = "multipart/form-data; boundary=cq" if multipart else "text/plain"
    result = await client.post(
        import_url, content=stream(), headers={**csrf_headers(client), "Content-Type": media}
    )
    assert_problem(result, 422, "cq.invalid_import")
