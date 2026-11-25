"""Identity tables: users, their server-side sessions and personal access tokens."""

from datetime import datetime
from enum import StrEnum
from typing import Literal, get_args
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, func, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ontology_platform.db import Base


class Role(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


_ROLE_VALUES = ", ".join(f"'{role.value}'" for role in Role)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({_ROLE_VALUES})", name="role"),
        {"schema": "identity"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]


class UserSession(Base):
    """A login session. Only the SHA-256 of the session token is stored."""

    __tablename__ = "sessions"
    __table_args__ = ({"schema": "identity"},)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        index=True,
    )
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)


# What an access token may do, on top of its owner's role (spec 003, section 4).
TokenScope = Literal["ontology:read", "objects:read", "changes:propose"]
TOKEN_SCOPES: tuple[TokenScope, ...] = get_args(TokenScope)
TOKEN_NAME_MAX_LENGTH = 100


class AccessToken(Base):
    """A personal access token for programs. Only the SHA-256 of the token is stored; the first
    characters are kept so that the owner can tell their tokens apart."""

    __tablename__ = "access_tokens"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiry"),
        {"schema": "identity"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(TOKEN_NAME_MAX_LENGTH))
    # "op_pat_" plus the first 8 characters of the random part.
    token_prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    last_used_at: Mapped[datetime | None]
    last_used_ip: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None]
    revoked_by: Mapped[UUID | None]
    # Limits the `token.rejected` audit events of one token to one per ten minutes.
    last_rejected_at: Mapped[datetime | None]
