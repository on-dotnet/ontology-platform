"""Personal access tokens (spec 003, section 4).

A token is `op_pat_` plus 43 URL-safe characters (256 random bits). Only its SHA-256 and its
first 15 characters are stored; the token itself is returned once, by `create_token`. Every
request looks the token up again, so revoking it, its expiry and deactivating its owner take
effect at once, and its scopes are cut down to what the owner's current role allows.
"""

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.identity import schemas
from ontology_platform.modules.identity.models import (
    TOKEN_SCOPES,
    AccessToken,
    Role,
    TokenScope,
    User,
)
from ontology_platform.modules.identity.service import Principal, hash_token, principal_of

# Recognizable by secret scanners: op_pat_[A-Za-z0-9_-]{43}
TOKEN_PREFIX = "op_pat_"  # noqa: S105
TOKEN_PATTERN = re.compile(r"op_pat_[A-Za-z0-9_-]{43}")
# "op_pat_" plus 8 characters of the random part, to tell tokens apart in a list.
SHOWN_PREFIX_LENGTH = len(TOKEN_PREFIX) + 8
MAX_LIVE_TOKENS = 10
LAST_USED_RESOLUTION = timedelta(minutes=1)
REJECTION_AUDIT_INTERVAL = timedelta(minutes=10)
# Expired and revoked tokens stay in the owner's list, greyed out, for this long.
LIST_DEAD_FOR = timedelta(days=30)

# The roles that may hold each scope; a token keeps only the scopes its owner's role allows.
SCOPE_ROLES: dict[TokenScope, frozenset[Role]] = {
    "ontology:read": frozenset(Role),
    "objects:read": frozenset(Role),
    "changes:propose": frozenset({Role.EDITOR, Role.REVIEWER, Role.ADMIN}),
}

TokenOwnerFilter = Literal["me", "all"]
RejectionReason = Literal["revoked", "expired", "inactive"]


@dataclass(frozen=True, slots=True)
class TokenContext:
    """A request authenticated with an access token."""

    principal: Principal
    token_id: UUID
    # The token's scopes that its owner's current role still allows.
    scopes: frozenset[TokenScope]


def invalid_token() -> AppError:
    # Unknown, expired, revoked or owner deactivated: deliberately indistinguishable.
    return AppError(401, "auth.invalid_token", "Invalid access token.")


def _new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _allowed_scopes(role: Role, scopes: list[str]) -> frozenset[TokenScope]:
    return frozenset(
        scope for scope in scopes if scope in TOKEN_SCOPES and role in SCOPE_ROLES[scope]
    )


def _audit_detail(token: AccessToken) -> dict[str, object]:
    # Id (the event's target), prefix and scopes only: never the token or its hash.
    return {"prefix": token.token_prefix, "scopes": sorted(token.scopes)}


def _info(token: AccessToken, owner: User) -> schemas.AccessToken:
    return schemas.AccessToken(
        id=token.id,
        name=token.name,
        prefix=token.token_prefix,
        scopes=sorted(cast(list[TokenScope], token.scopes)),
        owner=schemas.TokenOwner(id=owner.id, display_name=owner.display_name),
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
    )


def _live(now: datetime) -> ColumnElement[bool]:
    return and_(AccessToken.revoked_at.is_(None), AccessToken.expires_at > now)


async def list_tokens(
    db: AsyncSession,
    *,
    actor: Principal,
    owner: TokenOwnerFilter,
) -> list[schemas.AccessToken]:
    """The actor's tokens, or everyone's for an admin asking for `all`. Tokens that expired or
    were revoked more than 30 days ago are left out."""
    if owner == "all" and actor.role is not Role.ADMIN:
        raise AppError(403, "auth.forbidden", "Insufficient role.")
    cutoff = datetime.now(UTC) - LIST_DEAD_FOR
    statement = (
        select(AccessToken, User)
        .join(User, User.id == AccessToken.user_id)
        .where(
            AccessToken.expires_at > cutoff,
            or_(AccessToken.revoked_at.is_(None), AccessToken.revoked_at > cutoff),
        )
        .order_by(AccessToken.created_at.desc(), AccessToken.id)
    )
    if owner == "me":
        statement = statement.where(AccessToken.user_id == actor.id)
    return [_info(token, user) for token, user in (await db.execute(statement)).all()]


async def create_token(
    db: AsyncSession,
    body: schemas.AccessTokenCreate,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.AccessTokenCreated:
    """Issue a token for the actor. The token itself is only ever returned here."""
    scopes = sorted(set(body.scopes))
    if any(actor.role not in SCOPE_ROLES[scope] for scope in scopes):
        raise AppError(403, "token.scope_not_allowed", "Your role cannot request this scope.")
    # Serializes token creation per user, so concurrent requests cannot pass the limit. NO KEY
    # UPDATE: inserts elsewhere that reference the user (sessions, say) are not held up.
    owner = await db.scalar(select(User).where(User.id == actor.id).with_for_update(key_share=True))
    if owner is None:
        raise AppError(401, "auth.not_authenticated", "Authentication required.")
    now = datetime.now(UTC)
    live = select(func.count()).where(AccessToken.user_id == actor.id, _live(now))
    if (await db.scalar(live) or 0) >= MAX_LIVE_TOKENS:
        raise AppError(
            409,
            "token.limit_reached",
            f"At most {MAX_LIVE_TOKENS} active access tokens per user.",
        )
    secret = _new_token()
    token = AccessToken(
        user_id=actor.id,
        name=body.name,
        token_prefix=secret[:SHOWN_PREFIX_LENGTH],
        token_hash=hash_token(secret),
        scopes=scopes,
        created_at=now,
        expires_at=now + timedelta(days=body.expires_in_days),
    )
    db.add(token)
    await db.flush()
    audit.record(
        db,
        "token.created",
        actor_id=actor.id,
        target_type="access_token",
        target_id=str(token.id),
        detail=_audit_detail(token),
        ip=ip,
    )
    await db.commit()
    return schemas.AccessTokenCreated(token=secret, info=_info(token, owner))


async def revoke_token(
    db: AsyncSession,
    token_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> None:
    """Revoke one of the actor's tokens (any token for an admin). Revoking twice is a no-op."""
    statement = select(AccessToken).where(AccessToken.id == token_id).with_for_update()
    token = await db.scalar(statement)
    # Someone else's token looks the same as a missing one, except to an admin.
    if token is None or (token.user_id != actor.id and actor.role is not Role.ADMIN):
        raise AppError(404, "token.not_found", "Access token not found.")
    if token.revoked_at is not None:
        await db.rollback()
        return
    token.revoked_at = datetime.now(UTC)
    token.revoked_by = actor.id
    audit.record(
        db,
        "token.revoked",
        actor_id=actor.id,
        target_type="access_token",
        target_id=str(token.id),
        detail=_audit_detail(token),
        ip=ip,
    )
    await db.commit()


def _rejection(token: AccessToken, owner: User, now: datetime) -> RejectionReason | None:
    if token.revoked_at is not None:
        return "revoked"
    if now >= token.expires_at:
        return "expired"
    if not owner.is_active:
        return "inactive"
    return None


async def _record_rejection(
    db: AsyncSession, token: AccessToken, reason: RejectionReason, *, now: datetime, ip: str | None
) -> None:
    # The conditional update decides atomically which of concurrent requests gets to audit.
    claimed = await db.scalar(
        update(AccessToken)
        .where(
            AccessToken.id == token.id,
            or_(
                AccessToken.last_rejected_at.is_(None),
                AccessToken.last_rejected_at <= now - REJECTION_AUDIT_INTERVAL,
            ),
        )
        .values(last_rejected_at=now)
        .returning(AccessToken.id)
    )
    if claimed is None:
        return
    audit.record(
        db,
        "token.rejected",
        # No actor: whoever presented a refused token is not known.
        target_type="access_token",
        target_id=str(token.id),
        detail={**_audit_detail(token), "reason": reason},
        ip=ip,
    )
    await db.commit()


async def authenticate(db: AsyncSession, token: str, *, ip: str | None) -> TokenContext:
    """Resolve an access token or raise 401 `auth.invalid_token`."""
    if not TOKEN_PATTERN.fullmatch(token):
        raise invalid_token()
    statement = (
        select(AccessToken, User)
        .join(User, User.id == AccessToken.user_id)
        .where(AccessToken.token_hash == hash_token(token))
    )
    found = (await db.execute(statement)).one_or_none()
    if found is None:
        raise invalid_token()
    access_token, owner = found
    now = datetime.now(UTC)
    reason = _rejection(access_token, owner, now)
    if reason is not None:
        await _record_rejection(db, access_token, reason, now=now, ip=ip)
        raise invalid_token()
    touched = await db.execute(
        update(AccessToken)
        .where(
            AccessToken.id == access_token.id,
            or_(
                AccessToken.last_used_at.is_(None),
                AccessToken.last_used_at <= now - LAST_USED_RESOLUTION,
            ),
        )
        .values(last_used_at=now, last_used_ip=ip)
        .returning(AccessToken.id)
    )
    if touched.first() is not None:
        await db.commit()
    principal = principal_of(owner)
    return TokenContext(
        principal=principal,
        token_id=access_token.id,
        scopes=_allowed_scopes(principal.role, access_token.scopes),
    )
