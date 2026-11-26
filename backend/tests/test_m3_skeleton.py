"""The M3 skeleton (spec 003, section 16, batch 1): every new route exists with its final
access rules, answers 501 until its batch lands, and the shared pieces later batches build on
already work.
"""

import os
from typing import Any
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from httpx import AsyncClient, Response
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ai.schemas import BindingSuggestionCreate
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.connectors.statements import TableRef
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.query.schemas import ObjectSearch
from ontology_platform.settings import Settings
from support import csrf_headers
from test_ontology_support import sign_in

ID = "00000000-0000-4000-8000-000000000000"
Call = tuple[str, str, dict[str, Any] | None]

DATA_SOURCE = {
    "name": "钢铁 MES",
    "kind": "postgresql",
    "host": "postgres",
    "port": 5432,
    "database": "steel_mes",
    "username": "steel_reader",
    "password": "not-a-real-password",
}

# Who may call what (spec 003, section 13 and the appendix).
EVERYONE: list[Call] = []
# The binding suggestion routes (batch 4b) are tested in test_ai_binding_suggest.py.
EDITORS: list[Call] = []
ADMINS: list[Call] = []
ALL_CALLS = [*EVERYONE, *EDITORS, *ADMINS]


async def call(client: AsyncClient, request: Call) -> Response:
    method, path, body = request
    headers = csrf_headers(client) if "op_csrf" in client.cookies else {}
    return await client.request(method, path, json=body, headers=headers)


async def test_every_new_route_needs_a_session(client: AsyncClient) -> None:
    for request in ALL_CALLS:
        response = await call(client, request)
        assert response.status_code == 401, request
        assert response.json()["code"] == "auth.not_authenticated"


@pytest.mark.parametrize("role", list(Role))
async def test_roles_come_before_the_missing_implementations(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await sign_in(client, db, role)
    allowed = {
        "everyone": True,
        "editors": role in {Role.ADMIN, Role.EDITOR, Role.REVIEWER},
        "admins": role is Role.ADMIN,
    }
    for group, requests in (("everyone", EVERYONE), ("editors", EDITORS), ("admins", ADMINS)):
        for request in requests:
            response = await call(client, request)
            if allowed[group]:
                assert response.status_code == 501, request
                assert response.json()["code"] == "http.not_implemented"
            else:
                assert response.status_code == 403, request
                assert response.json()["code"] == "auth.forbidden"


@pytest.mark.parametrize("too_long", [False, True])
async def test_the_data_source_password_is_not_echoed_by_validation_errors(
    client: AsyncClient, db: AsyncSession, too_long: bool
) -> None:
    await sign_in(client, db, Role.ADMIN)
    secret = "s3cret-" + uuid4().hex + ("x" * 1024 if too_long else "")
    body = {**DATA_SOURCE, "password": secret}
    if not too_long:
        body["port"] = "not-a-port"

    response = await client.post("/api/data-sources", json=body, headers=csrf_headers(client))

    assert response.status_code == 422
    assert secret[:40] not in response.text


async def test_mcp_needs_an_access_token_even_with_a_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    anonymous = await client.post("/mcp", json={})
    await sign_in(client, db, Role.ADMIN)
    with_cookie = await client.post("/mcp", json={}, headers=csrf_headers(client))

    for response in (anonymous, with_cookie):
        assert response.status_code == 401
        assert response.json()["code"] == "auth.not_authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_mcp_is_not_part_of_the_openapi_document(client: AsyncClient) -> None:
    document = (await client.get("/api/openapi.json")).json()

    assert "/mcp" not in document["paths"]


async def test_the_catalog_read_other_modules_use_already_works(db: AsyncSession) -> None:
    source = DataSource(
        id=uuid4(),
        name="MES",
        kind="postgresql",
        host="postgres",
        port=5432,
        database="steel_mes",
        username="steel_reader",
    )
    db.add(source)
    await db.flush()
    db.add(
        CatalogTable(
            data_source_id=source.id,
            schema_name="mes",
            table_name="heat",
            kind="table",
            comment="炉次",
            columns=[
                {
                    "name": "heat_no",
                    "type": "character varying(20)",
                    "family": "string",
                    "nullable": False,
                    "comment": "炉次号",
                    "position": 1,
                }
            ],
            primary_key=["heat_no"],
            foreign_keys=[],
        )
    )
    await db.commit()

    ref = await connectors.get_data_source_ref(db, source.id)
    table = await connectors.get_catalog_table(db, source.id, TableRef("mes", "heat"))
    missing = await connectors.get_catalog_table(db, source.id, TableRef("mes", "coil"))

    assert ref is not None
    assert (ref.name, ref.status, ref.allow_samples) == ("MES", "active", False)
    assert (ref.has_credential, ref.catalog_status) == (False, "never")
    assert "host" not in ref.model_dump()
    assert "username" not in ref.model_dump()
    assert table is not None
    assert missing is None
    assert (table.schema_name, table.primary_key) == ("mes", ("heat_no",))
    assert table.columns[0].family == "string"
    assert await connectors.get_data_source_ref(db, uuid4()) is None
    by_schema = await connectors.list_catalog_tables_for(db, source.id, schema_names=("mes",))
    by_table = await connectors.list_catalog_tables_for(
        db, source.id, tables=(TableRef("mes", "heat"), TableRef("mes", "coil"))
    )
    assert [t.name for t in by_schema] == ["heat"]
    assert [t.name for t in by_table] == ["heat"]
    assert await connectors.list_catalog_tables_for(db, source.id, schema_names=("qms",)) == ()
    with pytest.raises(ValidationError):
        table.columns[0].name = "x"


async def test_unknown_table_usage_is_not_reported_as_unused(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(connectors, "_usage_provider", None)

    assert await connectors.table_usage(db, uuid4()) is None


def test_credential_encryption_works_on_this_cpu() -> None:
    """The Docker host's CPU has no SSE4.2, AVX or AES instructions (spec 003, 5.4)."""
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"op/datasource-credentials/v1"
    ).derive(b"x" * 32)
    box = AESGCM(key)
    nonce = os.urandom(12)
    data_source_id = uuid4().bytes

    sealed = box.encrypt(nonce, b'{"password": "p"}', data_source_id)

    assert box.decrypt(nonce, sealed, data_source_id) == b'{"password": "p"}'
    with pytest.raises(InvalidTag):
        box.decrypt(nonce, sealed, uuid4().bytes)


def test_new_settings_have_safe_defaults() -> None:
    settings = Settings(env="development")

    assert settings.previous_secret_keys == []
    assert (settings.query_timeout_seconds, settings.query_max_rows) == (15, 1000)
    assert settings.mcp_origins == []


def test_previous_secret_keys_are_split_and_kept_secret() -> None:
    settings = Settings(env="development", secret_key_previous=SecretStr(" old-1 , old-2,, "))

    assert [key.get_secret_value() for key in settings.previous_secret_keys] == ["old-1", "old-2"]
    assert "old-1" not in repr(settings)


@pytest.mark.parametrize(
    "scope",
    [{}, {"schemas": ["mes"], "tables": [{"schema": "mes", "name": "heat"}]}],
)
def test_a_binding_suggestion_names_exactly_one_scope(scope: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BindingSuggestionCreate.model_validate({"dataSourceId": ID, **scope})
    assert BindingSuggestionCreate.model_validate({"dataSourceId": ID, "schemas": ["mes"]})


def test_filters_accept_decimal_numbers() -> None:
    search = ObjectSearch.model_validate(
        {"typeId": ID, "filters": [{"propertyId": ID, "op": "gt", "value": 7.85}]}
    )

    assert search.filters[0].value == 7.85
