"""The connection layer (spec 003, 5.3): every connection to an external data source opens here.

Each connection is read-only twice over (the session default and an explicit READ ONLY
transaction), has connect, statement, lock and idle timeouts, is checked not to be the
platform's own database, and is closed after one operation. Driver exceptions never leave this
file: they become `connectors.errors` exceptions raised outside the `except` block, so no
exception chain carries the driver's message (it can name hosts, users and connection strings).
"""

import asyncio
import json
import logging
import re
import weakref
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from pydantic import SecretStr
from sqlalchemy import (
    BigInteger,
    Boolean,
    ColumnElement,
    Date,
    Integer,
    Numeric,
    SmallInteger,
    String,
    and_,
    bindparam,
    cast,
    column,
    false,
    or_,
    table,
    text,
)
from sqlalchemy import select as sql_select
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, REAL, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.types import NullType, TypeEngine, UserDefinedType

from ontology_platform.modules.connectors import catalog, config, schemas
from ontology_platform.modules.connectors.catalog import DiscoveredTable
from ontology_platform.modules.connectors.errors import (
    ConnectFailedError,
    ConnectorError,
    InvalidValueError,
    PlatformDatabaseError,
    QueryTimeoutError,
    SourceBusyError,
    SourceDisabledError,
    SourceMismatchError,
    SourceUnavailableError,
)
from ontology_platform.modules.connectors.models import (
    CatalogTable,
    DataSource,
    DataSourceKind,
    SslMode,
)
from ontology_platform.modules.connectors.secrets import open_password
from ontology_platform.modules.connectors.statements import (
    ColumnRef,
    Condition,
    Rows,
    SelectQuery,
    Side,
    SortKey,
    TableRef,
    Value,
)
from ontology_platform.settings import Settings

# Shown in pg_stat_activity of the data source, so its administrators can tell our sessions.
APPLICATION_NAME = "ontology-platform-connector"
CONNECT_TIMEOUT_SECONDS = 5
LOCK_TIMEOUT_MS = 2_000
IDLE_IN_TRANSACTION_TIMEOUT_MS = 60_000
# Statements per data source and process at the same time, and how long one waits for a turn.
MAX_CONCURRENT = 4
QUEUE_SECONDS = 5.0
TEXT_LIMIT = 2_000
SAMPLE_ROWS = 20
SAMPLES_PER_COLUMN = 5
SAMPLE_TEXT_LIMIT = 64

# psycopg logs failed connection attempts at DEBUG with host, port and the server's message,
# which names the user. Those lines must not reach any log, whatever level is configured.
logging.getLogger("psycopg").setLevel(logging.INFO)


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
    if row.status != "active" or row.secret is None:
        raise SourceDisabledError
    password = open_password(config.current(), row.id, row.secret, row.secret_key_id)
    return ConnectionParams(
        host=row.host,
        port=row.port,
        database=row.database,
        username=row.username,
        password=password,
        ssl_mode=row.ssl_mode,  # type: ignore[arg-type]
        kind=row.kind,  # type: ignore[arg-type]
    )


# ---------- not the platform's own database ----------


@dataclass(frozen=True, slots=True)
class _ServerIdentity:
    # pg_control_system().system_identifier, when the account may call it.
    system_identifier: str | None
    # pg_postmaster_start_time(), which every account may read: tells servers apart when the
    # system identifier is not available on one side.
    started_at: datetime
    database: str


_IDENTITY_ALLOWED = text(
    "SELECT has_function_privilege('pg_catalog.pg_control_system()', 'EXECUTE')"
)
_IDENTITY = text(
    "SELECT current_database(), pg_catalog.pg_postmaster_start_time(), "
    "(SELECT system_identifier::text FROM pg_catalog.pg_control_system())"
)
_IDENTITY_NO_ID = text("SELECT current_database(), pg_catalog.pg_postmaster_start_time(), NULL")


async def _identity_of(execute: Callable[[Any], Any]) -> _ServerIdentity:
    # Two statements: calling pg_control_system() without the privilege would fail the
    # transaction, and the platform's check runs in the caller's transaction.
    allowed = (await execute(_IDENTITY_ALLOWED)).scalar()
    statement = _IDENTITY if allowed else _IDENTITY_NO_ID
    database, started_at, system_identifier = (await execute(statement)).one()
    return _ServerIdentity(system_identifier, started_at, database)


_platform_identities: dict[str, _ServerIdentity] = {}


async def _platform_identity(db: AsyncSession) -> _ServerIdentity:
    key = db.get_bind().engine.url.render_as_string()
    identity = _platform_identities.get(key)
    if identity is None:
        identity = await _identity_of(db.execute)
        _platform_identities[key] = identity
    return identity


def _same_database(a: _ServerIdentity, b: _ServerIdentity) -> bool:
    if a.database != b.database:
        return False
    if a.system_identifier is not None and b.system_identifier is not None:
        return a.system_identifier == b.system_identifier
    return a.started_at == b.started_at


async def ensure_not_platform_address(
    db: AsyncSession, *, host: str, port: int, database: str
) -> None:
    """The check on saving and testing: refuse settings that name the platform's own database
    by host, port and database name. Raises PlatformDatabaseError. Connecting checks again by
    the server's identity, so another address of the same server is caught there."""
    url = db.get_bind().engine.url
    if (
        (url.host or "").lower() == host.strip().lower()
        and (url.port or 5432) == port
        and url.database == database
    ):
        raise PlatformDatabaseError


# ---------- connecting ----------


def _connect_failure(exc: BaseException) -> ConnectFailedError:
    """Classify a failed connection attempt. The message is only looked at, never kept."""
    if isinstance(exc, (pg_errors.ConnectionTimeout, TimeoutError)):
        return ConnectFailedError("timeout")
    sqlstate = getattr(exc, "sqlstate", None)
    message = str(exc).lower()
    if sqlstate in ("28P01", "28000") or "authentication failed" in message:
        reason = "auth_failed"
    elif sqlstate == "3D000" or ("database" in message and "does not exist" in message):
        reason = "database_missing"
    elif "ssl" in message:
        reason = "ssl"
    elif "timeout expired" in message:
        reason = "timeout"
    else:
        reason = "unreachable"
    return ConnectFailedError(reason, sqlstate=sqlstate)


def _options(settings: Settings) -> str:
    values = {
        "default_transaction_read_only": "on",
        "statement_timeout": settings.query_timeout_seconds * 1000,
        "lock_timeout": LOCK_TIMEOUT_MS,
        "idle_in_transaction_session_timeout": IDLE_IN_TRANSACTION_TIMEOUT_MS,
    }
    return " ".join(f"-c {name}={value}" for name, value in values.items())


async def _open(params: ConnectionParams, settings: Settings) -> psycopg.AsyncConnection[Any]:
    failure: ConnectFailedError | None = None
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS + 2):
            conn = await psycopg.AsyncConnection.connect(
                host=params.host,
                port=params.port,
                dbname=params.database,
                user=params.username,
                password=params.password.get_secret_value(),
                sslmode=params.ssl_mode,
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                application_name=APPLICATION_NAME,
                options=_options(settings),
            )
    except (psycopg.Error, OSError, TimeoutError) as exc:
        failure = _connect_failure(exc)
    if failure is not None:
        raise failure from None
    # Every transaction psycopg opens on this connection is BEGIN READ ONLY.
    await conn.set_read_only(True)
    return conn


def _statement_failure(exc: DBAPIError) -> ConnectorError:
    original = exc.orig
    sqlstate = getattr(original, "sqlstate", None)
    if isinstance(original, pg_errors.QueryCanceled) or sqlstate in ("57014", "55P03"):
        return QueryTimeoutError(sqlstate=sqlstate)
    if exc.connection_invalidated or (sqlstate or "").startswith("08") or sqlstate is None:
        return SourceUnavailableError(sqlstate=sqlstate)
    if sqlstate.startswith("22"):
        return InvalidValueError(sqlstate=sqlstate)
    return SourceMismatchError(sqlstate=sqlstate)


async def _cancel(conn: AsyncConnection) -> None:
    """Ask the server to cancel the running statement; best effort."""
    try:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        if isinstance(driver, psycopg.AsyncConnection):
            await driver.cancel_safe(timeout=CONNECT_TIMEOUT_SECONDS)
    except Exception:  # noqa: S110  (the connection is closed right after anyway)
        pass


@asynccontextmanager
async def connect(db: AsyncSession, params: ConnectionParams) -> AsyncIterator[AsyncConnection]:
    """A read-only connection inside a READ ONLY transaction, closed on exit.

    `db` is a session on the platform's database, for the identity check. Raises
    ConnectFailedError, PlatformDatabaseError; driver errors inside the block become
    `connectors.errors` exceptions as well. Cancelling the task cancels the running statement.
    """
    settings = config.current()
    platform = await _platform_identity(db)

    async def creator() -> psycopg.AsyncConnection[Any]:
        return await _open(params, settings)

    # The URL carries nothing: host, user and password stay with `creator`, out of SQLAlchemy's
    # reprs and pool logs.
    engine = create_async_engine(
        "postgresql+psycopg://",
        async_creator=creator,
        poolclass=NullPool,
        hide_parameters=True,
    )
    failure: ConnectorError | None = None
    try:
        async with engine.connect() as conn:
            try:
                async with conn.begin():
                    identity = await _identity_of(conn.execute)
                    if _same_database(identity, platform):
                        raise PlatformDatabaseError
                    yield conn
            except asyncio.CancelledError:
                await asyncio.shield(_cancel(conn))
                raise
            except DBAPIError as exc:
                failure = _statement_failure(exc)
    finally:
        await asyncio.shield(engine.dispose())
    if failure is not None:
        raise failure from None


# ---------- the operations ----------

_CAN_WRITE = text(
    """
    SELECT r.rolsuper
        OR has_database_privilege(current_database(), 'CREATE')
        OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_namespace n
            WHERE n.nspname NOT LIKE 'pg\\_%' AND n.nspname <> 'information_schema'
              AND has_schema_privilege(n.oid, 'CREATE'))
        OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND n.nspname NOT LIKE 'pg\\_%' AND n.nspname <> 'information_schema'
              AND has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE'))
    FROM pg_catalog.pg_roles r
    WHERE r.rolname = current_user
    """
)
_SERVER_VERSION = text("SELECT current_setting('server_version')")


async def test_connection(db: AsyncSession, params: ConnectionParams) -> schemas.ConnectionTest:
    """Connect, read the server version and whether the account may write.

    A failed connection is a result (`ok` false, `code` "datasource.connect_failed", `reason`),
    not an exception. Raises PlatformDatabaseError.
    """
    try:
        async with connect(db, params) as conn:
            version = (await conn.execute(_SERVER_VERSION)).scalar()
            can_write = bool((await conn.execute(_CAN_WRITE)).scalar())
    except ConnectFailedError as exc:
        return schemas.ConnectionTest(
            ok=False,
            code="datasource.connect_failed",
            reason=exc.reason,  # type: ignore[arg-type]
            warnings=[],
            server_version=None,
        )
    except QueryTimeoutError:
        return schemas.ConnectionTest(
            ok=False,
            code="datasource.connect_failed",
            reason="timeout",
            warnings=[],
            server_version=None,
        )
    except PlatformDatabaseError:
        raise
    except ConnectorError:
        return schemas.ConnectionTest(
            ok=False,
            code="datasource.connect_failed",
            reason="unreachable",
            warnings=[],
            server_version=None,
        )
    return schemas.ConnectionTest(
        ok=True,
        code=None,
        reason=None,
        warnings=["account_can_write"] if can_write else [],
        server_version=str(version) if version is not None else None,
    )


async def read_catalog(
    db: AsyncSession, params: ConnectionParams, schema_names: Sequence[str]
) -> list[DiscoveredTable]:
    """Connect and run `catalog.inspect_catalog`. Raises ConnectFailedError,
    PlatformDatabaseError, CatalogTooLargeError, and QueryTimeoutError past the statement
    timeout."""
    async with connect(db, params) as conn:
        return await conn.run_sync(catalog.inspect_catalog, tuple(schema_names))


# ---------- SelectQuery ----------

_PLAIN_NAME = r'(?:[a-z_][a-z0-9_$]*|"(?:[^"]|"")+")'
_TYPE_NAME = re.compile(rf"{_PLAIN_NAME}(?:\.{_PLAIN_NAME})?")


class _NamedType(UserDefinedType[str]):
    """A type the database names, such as an enum; the name comes from the catalog cache and is
    checked to be one quoted-or-plain, optionally schema-qualified identifier."""

    cache_ok = True

    def __init__(self, name: str) -> None:
        self.name = name

    def get_col_spec(self, **kw: Any) -> str:
        return self.name


def _bind_type(spec: schemas.CatalogColumn) -> TypeEngine[Any]:
    """The parameter type for comparisons with a column, from its cached source type."""
    source = spec.type.lower()
    match spec.family:
        case "string":
            return String()
        case "opaque":
            return PG_UUID(as_uuid=False) if source == "uuid" else NullType()
        case "integer":
            if source.startswith("smallint"):
                return SmallInteger()
            return BigInteger() if source.startswith("bigint") else Integer()
        case "decimal":
            if source.startswith("real"):
                return REAL()
            if source.startswith("double"):
                return DOUBLE_PRECISION()
            return Numeric()
        case "boolean":
            return Boolean()
        case "date":
            return Date()
        case "dateTime":
            return TIMESTAMP(timezone="with time zone" in source)
        case _:
            return NullType()


@dataclass(frozen=True, slots=True)
class _Columns:
    """The cached columns of the main and the joined table."""

    main: dict[str, schemas.CatalogColumn]
    joined: dict[str, schemas.CatalogColumn]

    def spec(self, ref: ColumnRef) -> schemas.CatalogColumn:
        found = (self.main if ref.side == "main" else self.joined).get(ref.name)
        if found is None:
            raise SourceMismatchError
        return found


class _Renderer:
    def __init__(self, query: SelectQuery, columns: _Columns) -> None:
        self.query = query
        self.columns = columns
        names: dict[Side, set[str]] = {"main": set(), "joined": set()}
        for ref in self._refs():
            names[ref.side].add(ref.name)
        if query.join is not None:
            for main_name, joined_name in query.join.on:
                names["main"].add(main_name)
                names["joined"].add(joined_name)
        self.main = self._table(query.table, names["main"], columns.main).alias("m")
        self.joined = (
            self._table(query.join.table, names["joined"], columns.joined).alias("j")
            if query.join is not None
            else None
        )

    def _refs(self) -> list[ColumnRef]:
        query = self.query
        return [
            *query.columns,
            *(condition.column for condition in query.where),
            *(key.column for key in query.order_by),
        ]

    @staticmethod
    def _table(ref: TableRef, names: set[str], specs: dict[str, schemas.CatalogColumn]) -> Any:
        missing = names - specs.keys()
        if missing:
            raise SourceMismatchError
        cols = [column(name, _bind_type(specs[name])) for name in sorted(names)]
        return table(ref.name, *cols, schema=ref.schema)

    def col(self, ref: ColumnRef) -> ColumnClause[Any]:
        source = self.main if ref.side == "main" else self.joined
        if source is None:
            raise ValueError("a joined column without a join")
        result: ColumnClause[Any] = source.c[ref.name]
        return result

    def param(self, ref: ColumnRef, value: Value) -> ColumnElement[Any]:
        if value is None:
            raise ValueError("comparison with None; use is_null")
        spec = self.columns.spec(ref)
        if spec.family == "opaque" and spec.type.lower() != "uuid":
            if not _TYPE_NAME.fullmatch(spec.type):
                raise SourceMismatchError
            return cast(bindparam(None, value, type_=String()), _NamedType(spec.type))
        return bindparam(None, value, type_=_bind_type(spec))

    def condition(self, condition: Condition) -> ColumnElement[bool]:
        col = self.col(condition.column)
        value = condition.value
        match condition.operator:
            case "is_null":
                return col.is_(None)
            case "not_null":
                return col.is_not(None)
            case "in":
                if not isinstance(value, tuple):
                    raise ValueError("`in` takes a tuple of values")
                if not value:
                    return false()
                return col.in_([self.param(condition.column, item) for item in value])
            case "contains" | "starts_with":
                if not isinstance(value, str):
                    raise ValueError(f"`{condition.operator}` takes a string")
                pattern = _like_escape(value)
                pattern = f"%{pattern}%" if condition.operator == "contains" else f"{pattern}%"
                return col.like(bindparam(None, pattern, type_=String()), escape="/")
        if isinstance(value, tuple):
            raise ValueError("a comparison takes one value")
        param = self.param(condition.column, value)
        match condition.operator:
            case "eq":
                return col == param
            case "ne":
                return col != param
            case "lt":
                return col < param
            case "le":
                return col <= param
            case "gt":
                return col > param
            case "ge":
                return col >= param
        raise ValueError(f"unknown operator {condition.operator!r}")

    def after(self, keys: tuple[SortKey, ...], values: tuple[Value, ...]) -> ColumnElement[bool]:
        """Rows after `values` in the order of `keys` (ascending NULLS LAST, descending NULLS
        FIRST: PostgreSQL's defaults, which its indexes serve)."""
        if len(keys) != len(values) or not keys:
            raise ValueError("`after` needs one value per sort key")
        branches: list[ColumnElement[bool]] = []
        equal: list[ColumnElement[bool]] = []
        for key, value in zip(keys, values, strict=True):
            col = self.col(key.column)
            if key.descending:
                beyond = col.is_not(None) if value is None else col < self.param(key.column, value)
            else:
                beyond = (
                    false()
                    if value is None
                    else or_(col > self.param(key.column, value), col.is_(None))
                )
            branches.append(and_(*equal, beyond) if equal else beyond)
            equal.append(col.is_(None) if value is None else col == self.param(key.column, value))
        return or_(*branches)

    def render(self, limit: int) -> Any:
        query = self.query
        selected = [self.col(ref).label(f"c{index}") for index, ref in enumerate(query.columns)]
        source = self.main
        if self.joined is not None and query.join is not None:
            on = [self.main.c[a] == self.joined.c[b] for a, b in query.join.on]
            if not on:
                raise ValueError("a join needs columns")
            source = self.main.join(self.joined, and_(*on))
        statement = sql_select(*selected).select_from(source)
        conditions = [self.condition(condition) for condition in query.where]
        if query.after is not None:
            conditions.append(self.after(query.order_by, query.after))
        if conditions:
            statement = statement.where(*conditions)
        order = []
        for key in query.order_by:
            col = self.col(key.column)
            order.append(col.desc().nulls_first() if key.descending else col.asc().nulls_last())
        return statement.order_by(*order).limit(limit)


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalize(value: Any) -> tuple[Value, bool]:
    """A driver value as a `Value`, and whether text was cut at TEXT_LIMIT."""
    if value is None or isinstance(value, (bool, int, Decimal, date, datetime)):
        return value, False
    if isinstance(value, float):
        return Decimal(repr(value)), False
    if isinstance(value, UUID):
        return str(value), False
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text_value = value if isinstance(value, str) else str(value)
    if len(text_value) > TEXT_LIMIT:
        return text_value[:TEXT_LIMIT], True
    return text_value, False


_limits: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[UUID, asyncio.Semaphore]] = (
    weakref.WeakKeyDictionary()
)


@asynccontextmanager
async def _turn(data_source_id: UUID) -> AsyncIterator[None]:
    """At most MAX_CONCURRENT statements per data source in this process; SourceBusyError after
    QUEUE_SECONDS in the queue."""
    per_loop = _limits.setdefault(asyncio.get_running_loop(), {})
    semaphore = per_loop.setdefault(data_source_id, asyncio.Semaphore(MAX_CONCURRENT))
    try:
        async with asyncio.timeout(QUEUE_SECONDS):
            await semaphore.acquire()
    except TimeoutError:
        raise SourceBusyError from None
    try:
        yield
    finally:
        semaphore.release()


async def _cached_columns(
    db: AsyncSession, data_source_id: UUID, ref: TableRef
) -> dict[str, schemas.CatalogColumn]:
    row = await db.scalar(
        sql_select(CatalogTable).where(
            CatalogTable.data_source_id == data_source_id,
            CatalogTable.schema_name == ref.schema,
            CatalogTable.table_name == ref.name,
        )
    )
    if row is None:
        raise SourceMismatchError
    specs = (schemas.CatalogColumn.model_validate(item) for item in row.columns)
    return {spec.name: spec for spec in specs}


async def _source_params(db: AsyncSession, data_source_id: UUID) -> ConnectionParams:
    row = await db.get(DataSource, data_source_id)
    if row is None:
        raise SourceDisabledError
    return params_of(row)


async def _execute(
    db: AsyncSession, data_source_id: UUID, statement: Any, fetch: int
) -> list[tuple[Any, ...]]:
    params = await _source_params(db, data_source_id)
    settings = config.current()
    async with _turn(data_source_id):
        try:
            async with asyncio.timeout(settings.query_timeout_seconds + CONNECT_TIMEOUT_SECONDS):
                async with connect(db, params) as conn:
                    result = await conn.execute(statement)
                    return [tuple(row) for row in result.fetchmany(fetch)]
        except TimeoutError:
            raise QueryTimeoutError from None


async def run_select(db: AsyncSession, query: SelectQuery) -> Rows:
    """`connectors.service.select`."""
    if query.limit < 1:
        raise ValueError("limit must be at least 1")
    if not query.columns:
        raise ValueError("a query needs columns")
    main = await _cached_columns(db, query.data_source_id, query.table)
    joined = (
        await _cached_columns(db, query.data_source_id, query.join.table)
        if query.join is not None
        else {}
    )
    limit = min(query.limit, config.current().query_max_rows)
    statement = _Renderer(query, _Columns(main, joined)).render(limit + 1)
    fetched = await _execute(db, query.data_source_id, statement, limit + 1)
    rows: list[tuple[Value, ...]] = []
    truncated: set[tuple[int, int]] = set()
    for row_index, raw in enumerate(fetched[:limit]):
        values: list[Value] = []
        for column_index, item in enumerate(raw):
            value, cut = _normalize(item)
            values.append(value)
            if cut:
                truncated.add((row_index, column_index))
        rows.append(tuple(values))
    return Rows(rows=tuple(rows), has_more=len(fetched) > limit, truncated=frozenset(truncated))


async def run_samples(
    db: AsyncSession, data_source_id: UUID, table: TableRef, columns: tuple[str, ...]
) -> dict[str, tuple[Value, ...]]:
    """`connectors.service.sample_values`."""
    row = await db.get(DataSource, data_source_id)
    if row is None or not row.allow_samples:
        raise SourceDisabledError
    if not columns:
        return {}
    query = SelectQuery(
        data_source_id=data_source_id,
        table=table,
        columns=tuple(ColumnRef(name) for name in columns),
        limit=SAMPLE_ROWS,
    )
    result = await run_select(db, query)
    samples: dict[str, list[Value]] = {name: [] for name in columns}
    for values in result.rows:
        for name, value in zip(columns, values, strict=True):
            if isinstance(value, str):
                value = value[:SAMPLE_TEXT_LIMIT]
            found = samples[name]
            if value is not None and value not in found and len(found) < SAMPLES_PER_COLUMN:
                found.append(value)
    return {name: tuple(values) for name, values in samples.items()}
