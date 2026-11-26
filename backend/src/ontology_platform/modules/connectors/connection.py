"""The connection layer (spec 003, 5.3): every connection to an external data source opens here.

Each connection is read-only twice over (the session default and an explicit READ ONLY
transaction), has connect, statement, lock and idle timeouts, is checked not to be the
platform's own database, and is closed after one operation. Driver exceptions never leave this
file: they become `connectors.errors` exceptions with the chain cut (`from None`), because the
driver's message can name hosts, users and connection strings.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ontology_platform.modules.connectors import schemas
from ontology_platform.modules.connectors.catalog import DiscoveredTable
from ontology_platform.modules.connectors.models import DataSource, DataSourceKind, SslMode
from ontology_platform.modules.connectors.statements import Rows, SelectQuery, TableRef, Value


@dataclass(frozen=True, slots=True)
class ConnectionParams:
    host: str
    port: int
    database: str
    username: str
    # Kept out of reprs, so that no traceback or log line shows it.
    password: SecretStr = field(repr=False)
    ssl_mode: SslMode = "prefer"
    kind: DataSourceKind = "postgresql"


def params_of(row: DataSource) -> ConnectionParams:
    """The saved settings of a data source with its password decrypted.

    Raises SourceDisabledError when the data source is archived or has no credentials, and
    CredentialUnreadableError when they cannot be decrypted.
    """
    raise NotImplementedError("M3 batch 3: connection layer")


async def ensure_not_platform_address(
    db: AsyncSession, *, host: str, port: int, database: str
) -> None:
    """The check on saving and testing: refuse settings that name the platform's own database
    by host, port and database name. Raises PlatformDatabaseError. Connecting checks again by
    the server's identity, so another address of the same server is caught there."""
    raise NotImplementedError("M3 batch 3: connection layer")


@asynccontextmanager
async def connect(db: AsyncSession, params: ConnectionParams) -> AsyncIterator[AsyncConnection]:
    """A read-only connection inside a READ ONLY transaction, closed on exit.

    `db` is a session on the platform's database, for the identity check. Raises
    ConnectFailedError, PlatformDatabaseError.
    """
    raise NotImplementedError("M3 batch 3: connection layer")
    yield  # pragma: no cover


async def test_connection(db: AsyncSession, params: ConnectionParams) -> schemas.ConnectionTest:
    """Connect, read the server version and whether the account may write.

    A failed connection is a result (`ok` false, `code` "datasource.connect_failed", `reason`),
    not an exception. Raises PlatformDatabaseError.
    """
    raise NotImplementedError("M3 batch 3: connection layer")


async def read_catalog(
    db: AsyncSession, params: ConnectionParams, schema_names: Sequence[str]
) -> list[DiscoveredTable]:
    """Connect and run `catalog.inspect_catalog`. Raises ConnectFailedError,
    PlatformDatabaseError, CatalogTooLargeError, and QueryTimeoutError past the statement
    timeout."""
    raise NotImplementedError("M3 batch 3: connection layer")


async def run_select(db: AsyncSession, query: SelectQuery) -> Rows:
    """`connectors.service.select`."""
    raise NotImplementedError("M3 batch 3: connection layer")


async def run_samples(
    db: AsyncSession, data_source_id: UUID, table: TableRef, columns: tuple[str, ...]
) -> dict[str, tuple[Value, ...]]:
    """`connectors.service.sample_values`."""
    raise NotImplementedError("M3 batch 3: connection layer")
