"""Identity API models."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from ontology_platform.modules.identity.models import (
    TOKEN_NAME_MAX_LENGTH,
    TOKEN_SCOPES,
    Role,
    TokenScope,
)
from ontology_platform.schemas import CamelModel


class LoginRequest(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class UserInfo(CamelModel):
    id: UUID
    username: str
    display_name: str
    role: Role


# ---------- access tokens (spec 003 §4) ----------

TOKEN_DEFAULT_DAYS = 90
TOKEN_MAX_DAYS = 365
TokenName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TOKEN_NAME_MAX_LENGTH),
]


class TokenOwner(CamelModel):
    id: UUID
    display_name: str


class AccessToken(CamelModel):
    id: UUID
    name: str
    # "op_pat_" plus 8 characters: enough to recognize a token, useless for signing in.
    prefix: str
    scopes: list[TokenScope]
    owner: TokenOwner
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class AccessTokenCreate(CamelModel):
    name: TokenName
    scopes: list[TokenScope] = Field(min_length=1, max_length=len(TOKEN_SCOPES))
    expires_in_days: int = Field(default=TOKEN_DEFAULT_DAYS, ge=1, le=TOKEN_MAX_DAYS)


class AccessTokenCreated(CamelModel):
    """The only response that ever carries the token itself."""

    token: str = Field(repr=False)
    info: AccessToken
