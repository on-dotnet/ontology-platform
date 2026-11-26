"""Accounts, password hashing and server-side sessions."""

import asyncio
import functools
import hashlib
import secrets
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.identity.models import Role, User, UserSession
from ontology_platform.settings import Settings

# Argon2id with the RFC 9106 low-memory profile (the argon2-cffi defaults).
_hasher = PasswordHasher()

# Argon2 is CPU and memory heavy (64 MiB per hash): run it off the event loop, a few at a time.
ARGON2_CONCURRENCY = 4
_argon2_slots = asyncio.Semaphore(ARGON2_CONCURRENCY)

LAST_SEEN_RESOLUTION = timedelta(minutes=1)
USER_AGENT_MAX_LENGTH = 512


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated user as other modules see it."""

    id: UUID
    username: str
    display_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class AuthContext:
    principal: Principal
    session_id: UUID
    csrf_token: str


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Raw tokens for the client; the database only keeps the session token's hash."""

    token: str
    csrf_token: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _run_argon2[**P, T](func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    async with _argon2_slots:
        return await asyncio.to_thread(func, *args, **kwargs)


async def hash_password(password: str) -> str:
    return await _run_argon2(_hasher.hash, password)


@functools.cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


def _verify_password(password_hash: str | None, password: str) -> bool:
    # Unknown users are checked against a dummy hash so response time does not reveal them.
    try:
        _hasher.verify(password_hash or _dummy_hash(), password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None


async def verify_password(password_hash: str | None, password: str) -> bool:
    """Check a password. Without a stored hash a dummy check still runs, then fails."""
    return await _run_argon2(_verify_password, password_hash, password)


def principal_of(user: User) -> Principal:
    return Principal(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=Role(user.role),
    )


def _failure_reason(user: User | None, password_ok: bool) -> str | None:
    if user is None:
        return "unknown_user"
    if not password_ok:
        return "bad_password"
    if not user.is_active:
        return "inactive"
    return None


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    role: Role,
    display_name: str | None = None,
    is_active: bool = True,
) -> User:
    """Add a user to the caller's transaction."""
    user = User(
        username=username,
        display_name=display_name or username,
        password_hash=await hash_password(password),
        role=role.value,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def ensure_admin(db: AsyncSession, username: str, password: str) -> bool:
    """Create the initial admin if there are no users at all. Returns whether it was created."""
    if await db.scalar(select(User.id).limit(1)) is not None:
        return False
    password_hash = await hash_password(password)
    statement = insert(User).values(
        username=username,
        display_name=username,
        password_hash=password_hash,
        role=Role.ADMIN.value,
    )
    statement = statement.on_conflict_do_nothing(index_elements=[User.username])
    user_id = await db.scalar(statement.returning(User.id))
    if user_id is not None:
        audit.record(
            db,
            "identity.admin_created",
            target_type="user",
            target_id=str(user_id),
            detail={"username": username},
        )
    await db.commit()
    return user_id is not None


async def login(
    db: AsyncSession,
    settings: Settings,
    *,
    username: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
    previous_token: str | None = None,
) -> tuple[Principal, IssuedSession]:
    """Check credentials and open a session, replacing `previous_token`'s session if given.

    All failures look the same to the caller.
    """
    user = await db.scalar(select(User).where(User.username == username))
    stored_hash = user.password_hash if user else None
    password_ok = await verify_password(stored_hash, password)
    reason = _failure_reason(user, password_ok)
    if user is None or reason is not None:
        audit.record(
            db,
            "auth.login_failed",
            target_type="user" if user else None,
            target_id=str(user.id) if user else None,
            detail={"username": username, "reason": reason},
            ip=ip,
        )
        await db.commit()
        raise AppError(401, "auth.invalid_credentials", "Invalid username or password.")

    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await hash_password(password)
    if previous_token:
        replaced = delete(UserSession).where(UserSession.token_hash == hash_token(previous_token))
        await db.execute(replaced)
    now = datetime.now(UTC)
    issued = IssuedSession(token=secrets.token_urlsafe(32), csrf_token=secrets.token_urlsafe(32))
    user_session = UserSession(
        token_hash=hash_token(issued.token),
        user_id=user.id,
        csrf_token=issued.csrf_token,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_absolute_days),
        ip=ip,
        user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None,
    )
    db.add(user_session)
    user.last_login_at = now
    audit.record(
        db,
        "auth.login_succeeded",
        actor_id=user.id,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username},
        ip=ip,
    )
    await db.commit()
    return principal_of(user), issued


async def authenticate(db: AsyncSession, settings: Settings, token: str) -> AuthContext | None:
    """Resolve a session token. Idle, expired or deactivated sessions are deleted."""
    statement = select(UserSession).where(UserSession.token_hash == hash_token(token))
    user_session = await db.scalar(statement)
    if user_session is None:
        return None
    now = datetime.now(UTC)
    idle_limit = timedelta(hours=settings.session_idle_hours)
    expired = now >= user_session.expires_at or now - user_session.last_seen_at >= idle_limit
    if expired or not user_session.user.is_active:
        await db.delete(user_session)
        await db.commit()
        return None
    if now - user_session.last_seen_at >= LAST_SEEN_RESOLUTION:
        user_session.last_seen_at = now
        await db.commit()
    return AuthContext(
        principal=principal_of(user_session.user),
        session_id=user_session.id,
        csrf_token=user_session.csrf_token,
    )


async def logout(db: AsyncSession, context: AuthContext, *, ip: str | None) -> None:
    await db.execute(delete(UserSession).where(UserSession.id == context.session_id))
    audit.record(
        db,
        "auth.logout",
        actor_id=context.principal.id,
        target_type="user",
        target_id=str(context.principal.id),
        ip=ip,
    )
    await db.commit()


async def display_names(db: AsyncSession, user_ids: Collection[UUID]) -> dict[UUID, str]:
    if not user_ids:
        return {}
    statement = select(User.id, User.display_name).where(User.id.in_(user_ids))
    return {row.id: row.display_name for row in await db.execute(statement)}
