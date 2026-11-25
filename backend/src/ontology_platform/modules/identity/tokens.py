"""Personal access tokens (spec 003, section 4).

The table, the API models and the routes are fixed by the M3 skeleton; creating, listing,
revoking and authenticating with tokens arrive with batch 2.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import not_implemented
from ontology_platform.modules.identity import schemas
from ontology_platform.modules.identity.service import Principal

# Recognizable by secret scanners: op_pat_[A-Za-z0-9_-]{43}
TOKEN_PREFIX = "op_pat_"  # noqa: S105
TokenOwnerFilter = Literal["me", "all"]


async def list_tokens(
    db: AsyncSession,
    *,
    actor: Principal,
    owner: TokenOwnerFilter,
) -> list[schemas.AccessToken]:
    """The actor's tokens, or everyone's for an admin asking for `all`."""
    raise not_implemented("Listing access tokens")


async def create_token(
    db: AsyncSession,
    body: schemas.AccessTokenCreate,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.AccessTokenCreated:
    """Issue a token for the actor. The token itself is only ever returned here."""
    raise not_implemented("Creating access tokens")


async def revoke_token(
    db: AsyncSession,
    token_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> None:
    """Revoke one of the actor's tokens (any token for an admin)."""
    raise not_implemented("Revoking access tokens")
