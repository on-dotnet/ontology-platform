"""Identity API models."""

from uuid import UUID

from pydantic import Field

from ontology_platform.modules.identity.models import Role
from ontology_platform.schemas import CamelModel


class LoginRequest(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class UserInfo(CamelModel):
    id: UUID
    username: str
    display_name: str
    role: Role
