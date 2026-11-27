"""Import steel-demo format competency questions within the caller's transaction."""

import tomllib
from collections.abc import AsyncGenerator
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from ontology_platform.errors import AppError
from ontology_platform.modules.cq import service
from ontology_platform.modules.cq.models import CompetencyQuestionRow
from ontology_platform.modules.cq.schemas import (
    CompetencyQuestionCreate,
    CqExpectInput,
    CqImportResult,
    ObjectKeys,
    QuestionNote,
    QuestionText,
)
from ontology_platform.modules.ontology import service as ontology

_FILE_LIMIT = 64 * 1024
_QUESTION_LIMIT = 50
_MULTIPART_OVERHEAD = 8 * 1024


def _invalid(detail: str) -> AppError:
    return AppError(422, "cq.invalid_import", detail)


async def _read_upload(request: Request) -> bytes:
    media = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media not in {"text/plain", "multipart/form-data"}:
        raise _invalid("Expected text/plain or multipart/form-data.")
    multipart = media == "multipart/form-data"
    limit = _FILE_LIMIT + _MULTIPART_OVERHEAD if multipart else _FILE_LIMIT

    async def chunks() -> AsyncGenerator[bytes]:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                # Starlette closes any open multipart files when this exception escapes its stream.
                raise MultiPartException("The upload exceeds the 64 KiB file limit.")
            yield chunk

    try:
        if not multipart:
            data = bytearray()
            async for chunk in chunks():
                data.extend(chunk)
            return bytes(data)
        form = await MultiPartParser(request.headers, chunks(), max_files=1, max_fields=0).parse()
        try:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise _invalid("Expected one multipart file in the 'file' field.")
            content = await upload.read(_FILE_LIMIT + 1)
        finally:
            await form.close()
    except (ValueError, MultiPartException) as exc:
        raise _invalid(str(exc)) from exc
    if len(content) > _FILE_LIMIT:
        raise _invalid("The TOML file exceeds 64 KiB.")
    return content


class _FileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Answerable(_FileModel):
    kind: Literal["answerable"]


class _Objects(_FileModel):
    kind: Literal["objects"]
    type_iri: str = Field(alias="typeIri")
    keys: ObjectKeys


class _Number(_FileModel):
    kind: Literal["number"]
    number: Decimal = Field(allow_inf_nan=False)
    tolerance: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)


class _FileQuestion(_FileModel):
    text: QuestionText
    expect: Annotated[_Answerable | _Objects | _Number, Field(discriminator="kind")]
    note: QuestionNote | None = None

    @field_validator("text", "note")
    @classmethod
    def _no_nul(cls, value: str | None) -> str | None:
        if value and "\x00" in value:
            raise ValueError("Text cannot contain a null character.")
        return value

    def as_create(self, types: dict[str, UUID]) -> CompetencyQuestionCreate:
        expect: CqExpectInput
        if isinstance(self.expect, _Objects):
            type_id = types.get(self.expect.type_iri)
            if type_id is None:
                raise _invalid("expect.typeIri does not name an object type in this ontology.")
            expect = {"kind": "objects", "type_id": type_id, "keys": self.expect.keys}
        elif isinstance(self.expect, _Number):
            expect = {
                "kind": "number",
                "number": str(self.expect.number),
                "tolerance": str(self.expect.tolerance),
            }
        else:
            expect = {"kind": "answerable"}
        body: CompetencyQuestionCreate = {"text": self.text, "expect": expect}
        if self.note is not None:
            body["note"] = self.note
        return body


def _parse(content: bytes) -> list[_FileQuestion]:
    try:
        document = tomllib.loads(content.decode("utf-8"), parse_float=Decimal)
    except (ValueError, InvalidOperation, RecursionError) as exc:
        raise _invalid(f"Invalid UTF-8 TOML: {exc}") from exc
    entries = document.get("questions")
    if document.keys() != {"questions"} or not isinstance(entries, list):
        raise _invalid("Expected an array of [[questions]] tables.")
    if len(entries) > _QUESTION_LIMIT:
        raise _invalid("At most 50 questions can be imported at once.")
    questions: list[_FileQuestion] = []
    for index, entry in enumerate(entries, start=1):
        try:
            questions.append(_FileQuestion.model_validate(entry))
        except ValidationError as exc:
            issue = exc.errors(include_input=False)[0]
            path = ".".join(str(part) for part in issue["loc"])
            raise _invalid(f"questions[{index}] {path}: {issue['msg']}") from exc
    return questions


async def import_questions(
    db: AsyncSession, ontology_id: UUID, request: Request, user_id: UUID
) -> CqImportResult:
    await ontology.lock_ontology(db, ontology_id)
    questions = _parse(await _read_upload(request))
    if not questions:
        return CqImportResult(created=0, skipped=0)
    types: dict[str, UUID] = {}
    if any(isinstance(q.expect, _Objects) for q in questions):
        type_iris = await service.object_types(db, ontology_id)
        types = {iri: type_id for type_id, iri in type_iris.items() if iri}
    prepared: dict[str, CompetencyQuestionRow] = {}
    for index, question in enumerate(questions, start=1):
        try:
            body = question.as_create(types)
            row = await service.prepare_question(db, ontology_id, body, user_id)
        except AppError as exc:
            if exc.status != 422:
                raise
            raise _invalid(f"questions[{index}]: {exc.detail}") from exc
        prepared.setdefault(row.text, row)

    # Reimporting must preserve both edited and archived questions with the same text.
    existing = select(CompetencyQuestionRow.text).where(
        CompetencyQuestionRow.ontology_id == ontology_id,
        CompetencyQuestionRow.text.in_(list(prepared)),
    )
    seen = set(await db.scalars(existing))
    rows = [row for text, row in prepared.items() if text not in seen]
    if rows:
        await service.append_questions(db, ontology_id, rows)
    return CqImportResult(created=len(rows), skipped=len(questions) - len(rows))
