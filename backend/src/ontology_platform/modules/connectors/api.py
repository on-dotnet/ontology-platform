"""HTTP routes of the connectors module (spec 003 appendix, "数据源").

Roles: everyone signed in sees the list (viewers without connection details); editors and
above test saved data sources and read the catalog; only admins create, change, archive and
test unsaved settings. None of these routes accepts an access token.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ontology_platform.db import DbSession
from ontology_platform.errors import problem_responses
from ontology_platform.modules.connectors import schemas, service
from ontology_platform.modules.connectors.statements import TableRef
from ontology_platform.modules.identity.api import CurrentUser, client_ip, require_role
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal

Editor = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]
Admin = Annotated[Principal, Depends(require_role(Role.ADMIN))]

router = APIRouter(prefix="/api", tags=["connectors"])


@router.get("/data-sources", responses=problem_responses(401))
async def list_data_sources(user: CurrentUser, db: DbSession) -> list[schemas.DataSource]:
    """Every data source. Viewers get `connection` and `catalog` as null."""
    return await service.list_data_sources(db, actor=user)


@router.post("/data-sources", status_code=201, responses=problem_responses(401, 403, 409, 422))
async def create_data_source(
    body: schemas.DataSourceCreate,
    request: Request,
    user: Admin,
    db: DbSession,
) -> schemas.DataSource:
    """Save a data source. The password is stored encrypted and never returned."""
    return await service.create_data_source(db, body, actor=user, ip=client_ip(request))


@router.post("/data-sources/test", responses=problem_responses(401, 403, 404, 422))
async def test_connection(
    body: schemas.ConnectionTestRequest,
    request: Request,
    user: Admin,
    db: DbSession,
) -> schemas.ConnectionTest:
    """Test connection settings that are not saved yet."""
    return await service.test_connection(db, body, actor=user, ip=client_ip(request))


@router.get("/data-sources/{id}", responses=problem_responses(401, 404, 422))
async def get_data_source(id: UUID, user: CurrentUser, db: DbSession) -> schemas.DataSource:
    return await service.get_data_source(db, id, actor=user)


@router.patch("/data-sources/{id}", responses=problem_responses(401, 403, 404, 409, 422))
async def update_data_source(
    id: UUID,
    body: schemas.DataSourcePatch,
    request: Request,
    user: Admin,
    db: DbSession,
) -> schemas.DataSource:
    """Change the given fields; 409 `datasource.stale` when `revision` is not the current one."""
    return await service.update_data_source(db, id, body, actor=user, ip=client_ip(request))


@router.post("/data-sources/{id}/archive", responses=problem_responses(401, 403, 404, 409, 422))
async def archive_data_source(
    id: UUID,
    request: Request,
    user: Admin,
    db: DbSession,
) -> schemas.DataSource:
    """Archive the data source and erase its credentials; refused while bindings use it."""
    return await service.archive_data_source(db, id, actor=user, ip=client_ip(request))


@router.post("/data-sources/{id}/test", responses=problem_responses(401, 403, 404, 409, 422))
async def test_data_source(
    id: UUID,
    request: Request,
    user: Editor,
    db: DbSession,
) -> schemas.ConnectionTest:
    return await service.test_data_source(db, id, actor=user, ip=client_ip(request))


@router.post(
    "/data-sources/{id}/catalog/refresh",
    status_code=202,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def refresh_catalog(
    id: UUID,
    request: Request,
    user: Editor,
    db: DbSession,
) -> schemas.DataSource:
    """Read the catalog again in the background; poll the data source for the result."""
    return await service.request_catalog_refresh(db, id, actor=user, ip=client_ip(request))


@router.get(
    "/data-sources/{id}/catalog/schemas",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def list_catalog_schemas(
    id: UUID, user: Editor, db: DbSession
) -> list[schemas.CatalogSchema]:
    return await service.list_catalog_schemas(db, id)


@router.get(
    "/data-sources/{id}/catalog/tables",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def list_catalog_tables(
    id: UUID,
    user: Editor,
    db: DbSession,
    schema: Annotated[str | None, Query(max_length=128)] = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> schemas.CatalogTablePage:
    """Tables and views of the cached catalog, by schema and name."""
    return await service.list_catalog_tables(db, id, schema=schema, q=q, limit=limit, cursor=cursor)


@router.get(
    "/data-sources/{id}/catalog/tables/{schema}/{table}",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def get_catalog_table(
    id: UUID,
    schema: str,
    table: str,
    user: Editor,
    db: DbSession,
) -> schemas.CatalogTable:
    """One table with its columns, primary key and foreign keys."""
    return await service.get_catalog_table_detail(db, id, TableRef(schema=schema, name=table))
