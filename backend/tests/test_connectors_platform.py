"""A data source can never be the platform's own database (spec 003, 5.2)."""

import socket
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from external_source import ExternalSource
from ontology_platform.main import create_app
from ontology_platform.modules.connectors import config, connection
from ontology_platform.modules.connectors.connection import (
    ConnectionParams,
    connect,
    ensure_not_platform_address,
)
from ontology_platform.modules.connectors.errors import PlatformDatabaseError
from ontology_platform.modules.identity.models import Role, User
from ontology_platform.settings import Settings
from test_connectors_support import reader_params


def _platform(settings: Settings, **changes: object) -> ConnectionParams:
    url = make_url(settings.database_url)
    values: dict[str, object] = {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "database": url.database or "",
        "username": url.username or "",
        "password": SecretStr(url.password or ""),
    }
    values.update(changes)
    return ConnectionParams(**values)  # type: ignore[arg-type]


async def test_the_platform_address_is_refused_before_connecting(
    db: AsyncSession, settings: Settings, external_source: ExternalSource
) -> None:
    platform = _platform(settings)

    with pytest.raises(PlatformDatabaseError):
        await ensure_not_platform_address(
            db, host=platform.host.upper(), port=platform.port, database=platform.database
        )
    # Another database of the same server is a fine data source.
    await ensure_not_platform_address(
        db, host=platform.host, port=platform.port, database=external_source.database
    )


@pytest.mark.parametrize("address", ["ip", "alias"])
async def test_another_address_of_the_platform_database_is_refused_after_connecting(
    db: AsyncSession, settings: Settings, address: str
) -> None:
    platform = _platform(settings)
    host = socket.gethostbyname(platform.host) if address == "ip" else f"{platform.host}."
    params = _platform(settings, host=host)
    # The address check alone cannot tell: the connection check must.
    await ensure_not_platform_address(db, host=host, port=params.port, database=params.database)

    with pytest.raises(PlatformDatabaseError):
        async with connect(db, params):
            pass
    with pytest.raises(PlatformDatabaseError):
        await connection.test_connection(db, params)


async def test_the_sample_database_on_the_same_server_is_allowed(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    result = await connection.test_connection(db, reader_params(external_source))

    assert result.ok
    assert result.warnings == []
    assert result.server_version


async def test_the_identity_check_uses_the_system_identifier_for_a_plain_account(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    """Spec 003, 5.2 leaves it to batch 3 to find out whether an account without special
    privileges can read the server's system identifier; this pins the answer down."""
    async with connect(db, reader_params(external_source)) as conn:
        identity = await connection._identity_of(conn.execute)
        is_superuser = (await conn.execute(text("SHOW is_superuser"))).scalar()

    assert is_superuser == "off"
    assert identity.system_identifier is not None
    assert identity.database == external_source.database


@pytest.mark.parametrize("state", ["idle", "pending", "in_transaction"])
async def test_identity_check_preserves_the_callers_session(
    db: AsyncSession, external_source: ExternalSource, state: str
) -> None:

    loaded = (await db.scalars(select(User).limit(1))).first()
    assert loaded is not None
    await db.commit()
    new = User(
        username=f"identity-{uuid4().hex}",
        display_name="Pending",
        password_hash="unused",
        role=Role.VIEWER,
    )
    if state == "pending":
        db.add(new)
    if state == "in_transaction":
        await db.execute(text("SELECT 1"))
    connection._platform_identities.clear()
    await connection.test_connection(db, reader_params(external_source))
    assert "display_name" not in attributes.instance_state(loaded).expired_attributes
    assert loaded.display_name
    assert (new in db.new) is (state == "pending")
    if state == "idle":
        assert not db.in_transaction()
    if state == "in_transaction":
        assert db.in_transaction()


async def test_identity_check_accepts_a_session_bound_to_a_connection(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    # As the capability-question check does: a savepoint session on the caller's connection.
    async with AsyncSession(
        bind=await db.connection(), join_transaction_mode="create_savepoint"
    ) as nested:
        connection._platform_identities.clear()
        result = await connection.test_connection(nested, reader_params(external_source))

    assert result.ok


def test_the_app_configures_the_connectors_with_its_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "_configured", None)
    settings = Settings()

    create_app(settings)

    assert config.current() is settings
