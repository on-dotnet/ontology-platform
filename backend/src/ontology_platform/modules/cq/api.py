from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request, Response

from ontology_platform.db import DbSession
from ontology_platform.errors import problem_responses
from ontology_platform.modules.cq import importing, schemas, service
from ontology_platform.modules.identity.api import CurrentUser, require_role
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
from ontology_platform.settings import Settings, get_settings

Editor = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]
AppSettings = Annotated[Settings, Depends(get_settings)]
router = APIRouter(prefix="/api", tags=["cq"], responses=problem_responses(401, 403, 404, 422))

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


@router.get(
    _COLLECTION,
    responses={200: {"headers": {"X-Cq-Check-Running": {"schema": {"type": "boolean"}}}}},
)
async def list_competency_questions(
    id: UUID, user: CurrentUser, db: DbSession, response: Response, archived: bool = False
) -> schemas.CompetencyQuestionList:
    result = await service.list_questions(db, id, archived)
    response.headers["X-Cq-Check-Running"] = str(await service.batch_running(db, id)).lower()
    return result


@router.post(_COLLECTION, status_code=201)
async def create_competency_question(
    id: UUID, body: Annotated[schemas.CompetencyQuestionCreate, Body()], user: Editor, db: DbSession
) -> schemas.CompetencyQuestion:
    result = await service.create(db, id, body, user.id)
    await db.commit()
    return result


@router.patch(_QUESTION, responses=problem_responses(409))
async def patch_competency_question(
    id: UUID, body: Annotated[schemas.CompetencyQuestionPatch, Body()], user: Editor, db: DbSession
) -> schemas.CompetencyQuestion:
    result = await service.patch(db, id, body)
    await db.commit()
    return result


@router.post(_QUESTION + "/archive", responses=problem_responses(409))
async def archive_competency_question(
    id: UUID,
    user: Editor,
    db: DbSession,
    revision: Annotated[int | None, Body(embed=True, ge=1)] = None,
) -> schemas.CompetencyQuestion:
    result = await service.archive(db, id, revision)
    await db.commit()
    return result


@router.post(_COLLECTION + "/import", openapi_extra={"requestBody": _IMPORT_BODY})
async def import_competency_questions(
    id: UUID, request: Request, user: Editor, db: DbSession
) -> schemas.CqImportResult:
    result = await importing.import_questions(db, id, request, user.id)
    await db.commit()
    return result


@router.post(_QUESTION + "/check", status_code=202, responses=problem_responses(409))
async def check_competency_question(
    id: UUID, user: Editor, db: DbSession, settings: AppSettings
) -> schemas.CqCheck:
    db.info["qa_settings"] = settings
    [result] = await service.start_checks(db, id, user.id, batch=False)
    await db.commit()
    return result


@router.post(_COLLECTION + "/check", status_code=202, responses=problem_responses(409))
async def check_competency_questions(
    id: UUID, user: Editor, db: DbSession, settings: AppSettings
) -> schemas.CqCheckList:
    db.info["qa_settings"] = settings
    checks = await service.start_checks(db, id, user.id, batch=True)
    await db.commit()
    return schemas.CqCheckList(checks=checks)


@router.get(_COLLECTION + "/coverage", responses=problem_responses(409))
async def competency_question_coverage(
    id: UUID, user: CurrentUser, db: DbSession
) -> schemas.CqCoverage:
    return await service.coverage_report(db, id)
