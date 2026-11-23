"""HTTP routes of the ontology module: ontologies, the working version, change sets, releases.

Every route needs a session. Creating an ontology needs admin, editor or reviewer; reviewing,
merging, rejecting, publishing and activating need admin or reviewer.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from ontology_platform.db import DbSession
from ontology_platform.errors import PROBLEM_MEDIA_TYPE, problem_responses
from ontology_platform.modules.identity.api import CurrentUser, client_ip, require_role
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.ontology import schemas, service
from ontology_platform.modules.ontology.models import ChangeSetStatus, Kind

Creator = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]
Reviewer = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.REVIEWER))]
ExportFormat = Annotated[Literal["turtle"], Query(alias="format")]

_RELEASE_INVALID: dict[int | str, dict[str, Any]] = {
    422: {
        "model": schemas.ReleaseInvalidProblem,
        "description": "Invalid request, or the working version failed the publish checks",
    },
}


class TurtleResponse(Response):
    media_type = "text/turtle"


def _turtle(text: str, filename: str) -> Response:
    disposition = f'attachment; filename="{filename}"'
    return TurtleResponse(content=text, headers={"Content-Disposition": disposition})


router = APIRouter(prefix="/api", tags=["ontology"])


# ---------- ontologies and the working version ----------


@router.get("/ontologies", responses=problem_responses(401))
async def list_ontologies(user: CurrentUser, db: DbSession) -> list[schemas.OntologySummary]:
    """All ontologies with their active element counts and open change sets."""
    return await service.list_ontologies(db)


@router.post("/ontologies", status_code=201, responses=problem_responses(401, 403, 409, 422))
async def create_ontology(
    body: schemas.OntologyCreate,
    request: Request,
    user: Creator,
    db: DbSession,
) -> schemas.OntologySummary:
    """Create an empty ontology. Without `key`, an ASCII name becomes the key; other names get
    `ontology-` plus six random characters."""
    return await service.create_ontology(db, body, actor=user.id, ip=client_ip(request))


@router.get("/ontologies/{id}", responses=problem_responses(401, 404, 422))
async def get_ontology(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> schemas.OntologySummary:
    """One ontology with its counts."""
    return await service.get_ontology_summary(db, id)


@router.get("/ontologies/{id}/elements", responses=problem_responses(401, 404, 422))
async def list_elements(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    kind: Kind | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[schemas.Element]:
    """Elements of the working version; `q` searches local names, labels and synonyms."""
    return await service.list_elements(db, id, kind=kind, q=q)


@router.get(
    "/ontologies/{id}/elements/{elementId}",
    responses=problem_responses(401, 404, 422),
)
async def get_element(
    id: UUID,
    elementId: UUID,  # noqa: N803
    user: CurrentUser,
    db: DbSession,
) -> schemas.ElementDetail:
    """One element and where it came from: merged change items and their evidence."""
    return await service.get_element(db, id, elementId)


@router.get("/ontologies/{id}/graph", responses=problem_responses(401, 404, 422))
async def get_graph(id: UUID, user: CurrentUser, db: DbSession) -> schemas.Graph:
    """Object types as nodes; relations (domain to range) and subclass links as edges."""
    return await service.get_graph(db, id)


@router.get(
    "/ontologies/{id}/export",
    response_class=TurtleResponse,
    responses=problem_responses(401, 404, 422),
)
async def export_ontology(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    export_format: ExportFormat = "turtle",
) -> Response:
    """The working version as Turtle (OWL 2, SHACL, SKOS)."""
    turtle, filename = await service.export_working_version(db, id)
    return _turtle(turtle, filename)


# ---------- change sets ----------


@router.get("/change-sets", responses=problem_responses(401, 422))
async def list_change_sets(
    user: CurrentUser,
    db: DbSession,
    ontology_id: Annotated[UUID | None, Query(alias="ontologyId")] = None,
    status: ChangeSetStatus | None = None,
) -> list[schemas.ChangeSetSummary]:
    """Change sets, newest first, with the number of items per decision."""
    return await service.list_change_sets(db, ontology_id=ontology_id, status=status)


# Change set responses leave out unset fields, so that `proposed`, `edited` and `before` carry
# only the keys that were given (every other field is always set).
@router.get(
    "/change-sets/{id}",
    response_model_exclude_unset=True,
    responses=problem_responses(401, 404, 422),
)
async def get_change_set(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> schemas.ChangeSetDetail:
    """The change set with all items and their evidence."""
    return await service.get_change_set(db, id)


@router.patch(
    "/change-sets/{id}/items/{itemId}",
    response_model_exclude_unset=True,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def update_item(
    id: UUID,
    itemId: UUID,  # noqa: N803
    body: schemas.ItemDecisionPatch,
    user: Reviewer,
    db: DbSession,
) -> schemas.ChangeItem:
    """Decide, edit or annotate one item. `edited` is checked against the item's kind
    (422 `changeset.invalid_edit`); a merged or rejected change set answers 409
    `changeset.closed`."""
    return await service.update_item(db, id, itemId, body, actor=user.id)


@router.post(
    "/change-sets/{id}/decisions",
    response_model_exclude_unset=True,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def decide_items(
    id: UUID,
    body: schemas.BulkDecision,
    user: Reviewer,
    db: DbSession,
) -> schemas.ChangeSetDetail:
    """Apply one decision to several items."""
    return await service.decide_items(db, id, body, actor=user.id)


@router.post(
    "/change-sets/{id}/merge",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def merge_change_set(
    id: UUID,
    request: Request,
    user: Reviewer,
    db: DbSession,
) -> schemas.MergeResult:
    """Apply the accepted items in one transaction and report the skipped ones. Answers 409
    `changeset.pending_items` while any item is undecided."""
    return await service.merge_change_set(
        db,
        id,
        actor=user.id,
        ip=client_ip(request),
    )


@router.post(
    "/change-sets/{id}/reject",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def reject_change_set(
    id: UUID,
    request: Request,
    user: Reviewer,
    db: DbSession,
) -> schemas.ChangeSetSummary:
    """Reject the whole change set."""
    return await service.reject_change_set(
        db,
        id,
        actor=user.id,
        ip=client_ip(request),
    )


# ---------- releases ----------


@router.get("/ontologies/{id}/releases", responses=problem_responses(401, 404, 422))
async def list_releases(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[schemas.ReleaseSummary]:
    """Published versions, newest first."""
    return await service.list_releases(db, id)


@router.post(
    "/ontologies/{id}/releases",
    status_code=201,
    response_model=schemas.ReleaseSummary,
    responses={**problem_responses(401, 403, 404), **_RELEASE_INVALID},
)
async def publish_release(
    id: UUID,
    body: schemas.ReleaseCreate,
    request: Request,
    user: Reviewer,
    db: DbSession,
) -> schemas.ReleaseSummary | JSONResponse:
    """Publish the working version as the next version and make it current. When the checks
    fail: 422 `release.invalid` with a `problems` list."""
    try:
        return await service.publish_release(
            db,
            id,
            body,
            actor=user.id,
            ip=client_ip(request),
        )
    except service.ReleaseInvalidError as error:
        return JSONResponse(error.body(), status_code=error.status, media_type=PROBLEM_MEDIA_TYPE)


@router.get("/releases/{id}", responses=problem_responses(401, 404, 422))
async def get_release(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> schemas.ReleaseSummary:
    """One published version."""
    return await service.get_release(db, id)


@router.get(
    "/releases/{id}/export",
    response_class=TurtleResponse,
    responses=problem_responses(401, 404, 422),
)
async def export_release(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    export_format: ExportFormat = "turtle",
) -> Response:
    """The Turtle stored when the version was published."""
    turtle, filename = await service.export_release(db, id)
    return _turtle(turtle, filename)


@router.post(
    "/releases/{id}/activate",
    responses=problem_responses(401, 403, 404, 422),
)
async def activate_release(
    id: UUID,
    request: Request,
    user: Reviewer,
    db: DbSession,
) -> schemas.ReleaseSummary:
    """Make this version the current one (also used to roll back)."""
    return await service.activate_release(db, id, actor=user.id, ip=client_ip(request))
