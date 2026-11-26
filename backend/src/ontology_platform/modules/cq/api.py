from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request

from ontology_platform.errors import problem_responses
from ontology_platform.modules.cq import schemas, service
from ontology_platform.modules.identity.api import CurrentUser, require_role
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal

Editor = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]
router = APIRouter(prefix="/api", tags=["cq"], responses=problem_responses(401, 403, 404, 422, 501))

_COLLECTION = "/ontologies/{id}/competency-questions"
_QUESTION = "/competency-questions/{id}"
_IMPORT_BODY = {
    "required": True,
    "description": "TOML with up to 50 questions, at most 64 KiB.",
    "content": {
        "text/plain": {"schema": {"type": "string"}},
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
                "required": ["file"],
            }
        },
    },
}


@router.get(_COLLECTION)
async def list_competency_questions(
    id: UUID, user: CurrentUser, archived: bool = False
) -> schemas.CompetencyQuestionList:
    service.unavailable()


@router.post(_COLLECTION, status_code=201)
async def create_competency_question(
    id: UUID, body: Annotated[schemas.CompetencyQuestionCreate, Body()], user: Editor
) -> schemas.CompetencyQuestion:
    service.unavailable()


@router.patch(_QUESTION, responses=problem_responses(409))
async def patch_competency_question(
    id: UUID, body: Annotated[schemas.CompetencyQuestionPatch, Body()], user: Editor
) -> schemas.CompetencyQuestion:
    service.unavailable()


@router.post(_QUESTION + "/archive")
async def archive_competency_question(id: UUID, user: Editor) -> schemas.CompetencyQuestion:
    service.unavailable()


@router.post(_COLLECTION + "/import", openapi_extra={"requestBody": _IMPORT_BODY})
async def import_competency_questions(
    id: UUID, request: Request, user: Editor
) -> schemas.CqImportResult:
    service.unavailable()


@router.post(_QUESTION + "/check", status_code=202, responses=problem_responses(409))
async def check_competency_question(id: UUID, user: Editor) -> schemas.CqCheck:
    service.unavailable()


@router.post(_COLLECTION + "/check", status_code=202, responses=problem_responses(409))
async def check_competency_questions(id: UUID, user: Editor) -> schemas.CqCheckList:
    service.unavailable()


@router.get(_COLLECTION + "/coverage")
async def competency_question_coverage(id: UUID, user: CurrentUser) -> schemas.CqCoverage:
    service.unavailable()
