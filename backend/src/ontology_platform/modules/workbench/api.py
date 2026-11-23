"""HTTP routes of the workbench module."""

from fastapi import APIRouter

from ontology_platform.db import DbSession
from ontology_platform.errors import problem_responses
from ontology_platform.modules.identity.api import CurrentUser
from ontology_platform.modules.workbench import service
from ontology_platform.modules.workbench.schemas import WorkbenchSummary

router = APIRouter(prefix="/api", tags=["workbench"])


@router.get("/workbench/summary", responses=problem_responses(401))
async def get_summary(user: CurrentUser, db: DbSession) -> WorkbenchSummary:
    return await service.summary(db)
