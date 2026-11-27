"""HTTP routes of the ontology module: ontologies, the working version, change sets, releases.

Every route needs a session. Creating or importing an ontology, editing it by hand or in expert
mode, and withdrawing one's own change set need admin, editor or reviewer; reviewing, merging,
rejecting others' change sets, publishing and activating need admin or reviewer.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from ontology_platform.db import DbSession
from ontology_platform.errors import PROBLEM_MEDIA_TYPE, problem_responses
from ontology_platform.modules.identity.api import (
    CurrentUser,
    client_ip,
    require_role,
    require_scope,
)
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.ontology import (
    bindings,
    compare,
    editing,
    expert,
    importing,
    merge,
    r2rml,
    releases,
    schemas,
    service,
)
from ontology_platform.modules.ontology.models import ChangeSetStatus, Kind
from ontology_platform.modules.ontology.review_memory import MemoryKind
from ontology_platform.settings import Settings, get_settings

Creator = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]
Reviewer = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.REVIEWER))]
# Published versions are also open to access tokens with ontology:read (spec 003 appendix).
ReleaseReader = Annotated[Principal, Depends(require_scope("ontology:read"))]
AppSettings = Annotated[Settings, Depends(get_settings)]
ExportFormat = Annotated[Literal["turtle"], Query(alias="format")]
REVIEWER_ROLES = frozenset({Role.ADMIN, Role.REVIEWER})
_COMPARE_TARGET = r"^(working|[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
router = APIRouter(prefix="/api", tags=["ontology"])


@router.get("/ontologies/{id}/review-memory", responses=problem_responses(401, 404, 422))
async def list_review_memory(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    kind: MemoryKind | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> schemas.ReviewMemoryPage:
    return await service.list_review_memory(db, id, kind=kind, q=q, limit=limit, cursor=cursor)


@router.delete(
    "/ontologies/{id}/review-memory/{entryId}",
    status_code=204,
    responses=problem_responses(401, 403, 404, 422),
)
async def delete_review_memory(
    id: UUID,
    entryId: UUID,  # noqa: N803 (the path names it in camelCase)
    user: Reviewer,
    db: DbSession,
) -> None:
    await service.delete_review_memory(db, id, entryId, actor=user.id)


@router.post(
    "/ontologies/{id}/review-memory/{entryId}/restore",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def restore_review_memory(
    id: UUID,
    entryId: UUID,  # noqa: N803 (the path names it in camelCase)
    user: Reviewer,
    db: DbSession,
) -> schemas.ReviewMemoryEntry:
    return await service.restore_review_memory(db, id, entryId, actor=user.id)


@router.post(
    "/ontologies/{id}/review-memory/clear", responses=problem_responses(401, 403, 404, 422)
)
async def clear_review_memory(id: UUID, user: Reviewer, db: DbSession) -> schemas.ReviewMemoryClear:
    return await service.clear_review_memory(db, id, actor=user.id)


def _may_review_own(user: Principal, settings: Settings) -> bool:
    """Whether the user may decide and merge change sets they created (spec 002, section 8)."""
    return user.role in REVIEWER_ROLES and settings.review_mode == "single"


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


_IMPORT_ERRORS: dict[int | str, dict[str, Any]] = {
    **problem_responses(401, 403, 404, 409, 413, 415),
    422: {
        "model": schemas.ImportParseProblem,
        "description": "Invalid request, or the file is not valid Turtle / RDF/XML",
    },
}


def _import_problem(error: importing.ImportParseError) -> JSONResponse:
    return JSONResponse(error.body(), status_code=error.status, media_type=PROBLEM_MEDIA_TYPE)


@router.post(
    "/ontologies/import",
    status_code=201,
    response_model=schemas.ImportResult,
    responses=_IMPORT_ERRORS,
)
async def import_ontology(
    request: Request,
    user: Creator,
    db: DbSession,
    file: UploadFile,
    name: Annotated[str | None, Form(max_length=200)] = None,
    key: Annotated[str | None, Form(pattern=schemas.KEY_PATTERN)] = None,
) -> schemas.ImportResult | JSONResponse:
    """Create an ontology from a Turtle or RDF/XML file. Its content arrives as a change set
    (source `import`) to review and merge; what the platform cannot map is kept as axioms."""
    data = await file.read(importing.MAX_BYTES + 1)
    try:
        return await importing.import_new(
            db,
            data=data,
            filename=file.filename or "",
            name=name.strip() if name and name.strip() else None,
            key=key,
            actor=user.id,
            ip=client_ip(request),
        )
    except importing.ImportParseError as error:
        return _import_problem(error)


@router.post(
    "/ontologies/{id}/import",
    response_model=schemas.ImportResult,
    responses=_IMPORT_ERRORS,
)
async def import_into_ontology(
    id: UUID,
    request: Request,
    user: Creator,
    db: DbSession,
    file: UploadFile,
) -> schemas.ImportResult | JSONResponse:
    """Compare a file with the working version; the differences become an import change set
    (none when there are no differences)."""
    data = await file.read(importing.MAX_BYTES + 1)
    try:
        return await importing.import_into(
            db,
            id,
            data=data,
            filename=file.filename or "",
            actor=user.id,
            ip=client_ip(request),
        )
    except importing.ImportParseError as error:
        return _import_problem(error)


@router.post(
    "/ontologies/{id}/turtle",
    response_model=schemas.ImportResult,
    responses=_IMPORT_ERRORS,
)
async def edit_turtle(
    id: UUID,
    body: schemas.TurtleEdit,
    request: Request,
    user: Creator,
    db: DbSession,
) -> schemas.ImportResult | JSONResponse:
    """Expert mode: compare the edited Turtle of the whole working version with it; the
    differences become a manual change set that always goes to review."""
    try:
        return await expert.save_turtle(
            db,
            id,
            body.turtle,
            actor=user.id,
            ip=client_ip(request),
        )
    except importing.ImportParseError as error:
        return _import_problem(error)


@router.post(
    "/ontologies/{id}/edits",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def save_edits(
    id: UUID,
    body: schemas.EditRequest,
    request: Request,
    user: Creator,
    db: DbSession,
    settings: AppSettings,
) -> schemas.EditResult:
    """Save changes made by hand as a manual change set. With `apply`, a user who may review
    their own changes (admin or reviewer, single review mode) merges it at once; any item that
    would be skipped rolls everything back (409 `element.stale` or the item's code). Otherwise
    the change set stays open for review. 409 `element.stale` when a target moved on since it
    was read, `element.name_taken` for a taken local name or IRI; 422 `axiom.invalid` and
    `axiom.maps_to_element` for axiom fragments."""
    return await editing.save_edits(
        db,
        id,
        body,
        actor=user.id,
        may_apply=_may_review_own(user, settings),
        ip=client_ip(request),
    )


@router.get(
    "/ontologies/{id}/elements/{elementId}/impact",
    responses=problem_responses(401, 404, 422),
)
async def get_impact(
    id: UUID,
    elementId: UUID,  # noqa: N803
    user: CurrentUser,
    db: DbSession,
) -> schemas.Impact:
    """What refers to an element: subtypes, relations and properties, constraints, axioms, and
    its inverse. Deleting it takes these along (spec 002, section 6)."""
    return await editing.impact(db, id, elementId)


@router.get("/settings/platform", responses=problem_responses(401))
async def get_platform_settings(
    user: CurrentUser,
    settings: AppSettings,
) -> schemas.PlatformSettings:
    """Settings every page may need: the review mode."""
    return schemas.PlatformSettings(review_mode=settings.review_mode)


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
    status: Literal["active", "deprecated", "all"] = "active",
) -> list[schemas.Element]:
    """Elements of the working version (deleted ones with `status=deprecated` or `all`); `q`
    searches local names, labels, synonyms, IRIs and axiom text."""
    return await service.list_elements(db, id, kind=kind, q=q, status=status)


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


@router.get("/ontologies/{id}/bindings", responses=problem_responses(401, 403, 404, 422))
async def list_bindings(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    type_id: Annotated[UUID | None, Query(alias="typeId")] = None,
) -> list[schemas.TypeBindingView]:
    """The data bindings of the working version by object type (spec 003, 6.5): of one type
    (`typeId`, bound or not), or of every bound type, checked against the cached catalogs.
    404 `element.not_found` when `typeId` is not an active object type."""
    return await bindings.binding_views(db, id, type_id)


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
    settings: AppSettings,
) -> schemas.ChangeItem:
    """Decide, edit or annotate one item. `edited` is checked against the item's kind
    (422 `changeset.invalid_edit`); a merged or rejected change set answers 409
    `changeset.closed`; in separate review mode, 403 `changeset.self_review` for a decision or
    an edit on one's own change set. `matchDecision` (spec 004, 5.5) is the reviewer's
    conclusion about the item's alignment record: 422 `changeset.no_match` when there is none."""
    return await service.update_item(
        db,
        id,
        itemId,
        body,
        actor=user.id,
        review_mode=settings.review_mode,
    )


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
    settings: AppSettings,
) -> schemas.ChangeSetDetail:
    """Apply one decision to several items (403 `changeset.self_review` as for one item)."""
    return await service.decide_items(db, id, body, actor=user.id, review_mode=settings.review_mode)


@router.post(
    "/change-sets/{id}/merge",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def merge_change_set(
    id: UUID,
    request: Request,
    user: Reviewer,
    db: DbSession,
    settings: AppSettings,
    body: schemas.MergeRequest | None = None,
) -> schemas.MergeResult:
    """Apply the accepted items in one transaction and report the skipped ones. Answers 409
    `changeset.pending_items` while any item is undecided, 403 `changeset.self_review` in
    separate review mode for one's own change set, and 409 `changeset.resolution_changed`
    when the merge would not do what the `resolutionToken` sent with it stands for."""
    return await merge.merge_change_set(
        db,
        id,
        actor=user.id,
        ip=client_ip(request),
        review_mode=settings.review_mode,
        resolution_token=body.resolution_token if body else None,
    )


@router.post(
    "/change-sets/{id}/reject",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def reject_change_set(
    id: UUID,
    request: Request,
    user: Creator,
    db: DbSession,
) -> schemas.ChangeSetSummary:
    """Reject the whole change set. Reviewers may reject any; its creator may withdraw their
    own (403 `auth.forbidden` otherwise)."""
    return await service.reject_change_set(
        db,
        id,
        actor=user.id,
        may_reject_any=user.role in REVIEWER_ROLES,
        ip=client_ip(request),
    )


# ---------- releases ----------


@router.get("/ontologies/{id}/compare", responses=problem_responses(401, 404, 422))
async def compare_versions(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    from_: Annotated[UUID, Query(alias="from")],
    # One string type rather than `UUID | Literal["working"]`, whose generated client type
    # (`string | "working"`) collapses to string anyway.
    to: Annotated[str, Query(pattern=_COMPARE_TARGET)] = "working",
) -> schemas.Comparison:
    """What changed from a release (`to`: its id) to another release or to the working version
    (`to`: `working`), each change rated breaking, review or compatible (spec 002, section 9).
    404 `release.not_found` when a release does not belong to the ontology."""
    return await compare.compare(db, id, from_, "working" if to == "working" else UUID(to))


@router.get("/ontologies/{id}/releases", responses=problem_responses(401, 404, 422))
async def list_releases(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[schemas.ReleaseSummary]:
    """Published versions, newest first."""
    return await releases.list_releases(db, id)


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
        return await releases.publish_release(
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
    user: ReleaseReader,
    db: DbSession,
) -> schemas.ReleaseSummary:
    """One published version."""
    return await releases.get_release(db, id)


@router.get(
    "/releases/{id}/export",
    response_class=TurtleResponse,
    responses=problem_responses(401, 404, 422),
)
async def export_release(
    id: UUID,
    user: ReleaseReader,
    db: DbSession,
    export_format: ExportFormat = "turtle",
) -> Response:
    """The Turtle stored when the version was published."""
    turtle, filename = await releases.export_release(db, id)
    return _turtle(turtle, filename)


@router.get(
    "/releases/{id}/r2rml",
    response_class=TurtleResponse,
    responses=problem_responses(401, 403, 404, 422),
)
async def export_release_r2rml(id: UUID, user: Creator, db: DbSession) -> Response:
    """Download the R2RML mapping for this published version."""
    turtle, filename = await r2rml.export_release(db, id)
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
    return await releases.activate_release(db, id, actor=user.id, ip=client_ip(request))
