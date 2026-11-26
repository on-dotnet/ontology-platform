"""HTTP routes of the query module (spec 003 appendix, "对象查询").

Open to every signed-in user and to access tokens with the `objects:read` scope. Each handler
takes the request: a client that goes away cancels the statement in the data source (5.3).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request

from ontology_platform.db import DbSession
from ontology_platform.errors import problem_responses
from ontology_platform.modules.identity.api import require_scope
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.query import schemas, service

ObjectReader = Annotated[Principal, Depends(require_scope("objects:read"))]
ObjectKey = Annotated[str, Path(min_length=1, max_length=schemas.KEY_MAX_LENGTH)]

router = APIRouter(prefix="/api", tags=["query"])

_ERRORS = problem_responses(401, 403, 404, 409, 422, 502, 503, 504)


@router.get("/ontologies/{id}/objects/types", responses=problem_responses(401, 403, 404, 409, 422))
async def list_object_types(
    id: UUID,
    request: Request,
    user: ObjectReader,
    db: DbSession,
) -> schemas.ObjectTypeList:
    """The bound object types of the release in effect, with what can be filtered and followed."""
    return await service.list_types(db, id)


@router.post("/ontologies/{id}/objects/search", responses=_ERRORS)
async def search_objects(
    id: UUID,
    body: schemas.ObjectSearch,
    request: Request,
    user: ObjectReader,
    db: DbSession,
) -> schemas.ObjectPage:
    """List the objects of a type: filter, sort and page. A read, although it is a POST."""
    return await service.until_disconnected(request, service.search(db, id, body))


@router.get("/ontologies/{id}/objects/{typeId}/{key}", responses=_ERRORS)
async def get_object(
    id: UUID,
    typeId: UUID,  # noqa: N803
    key: ObjectKey,
    request: Request,
    user: ObjectReader,
    db: DbSession,
) -> schemas.ObjectDetail:
    """One object by type and primary key, with the relations it can be followed along."""
    return await service.until_disconnected(request, service.get_object(db, id, typeId, key))


@router.get("/ontologies/{id}/objects/{typeId}/{key}/related", responses=_ERRORS)
async def list_related_objects(
    id: UUID,
    typeId: UUID,  # noqa: N803
    key: ObjectKey,
    request: Request,
    user: ObjectReader,
    db: DbSession,
    relation_id: Annotated[UUID, Query(alias="relationId")],
    direction: schemas.Direction = "out",
    limit: Annotated[int, Query(ge=1, le=schemas.PAGE_MAX)] = schemas.PAGE_DEFAULT,
    cursor: Annotated[str | None, Query(max_length=schemas.CURSOR_MAX_LENGTH)] = None,
) -> schemas.ObjectPage:
    """One hop along a relation; `typeId` of the page is the type of the related objects."""
    return await service.until_disconnected(
        request,
        service.related(
            db,
            id,
            typeId,
            key,
            relation_id=relation_id,
            direction=direction,
            limit=limit,
            cursor=cursor,
        ),
    )
