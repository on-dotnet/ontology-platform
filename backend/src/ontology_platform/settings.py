"""Application settings, read from OP_* environment variables (empty values count as unset)."""

from typing import Literal, Self

from fastapi import Request
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development defaults; production refuses to start while any of them is still in use.
DEV_SECRET_KEY = "dev-only-secret-change-me"  # noqa: S105
DEV_ADMIN_PASSWORD = "admin12345"  # noqa: S105
DEV_DATABASE_PASSWORD = "ontology-dev-only"  # noqa: S105
DEV_DATABASE_URL = f"postgresql+psycopg://ontology:{DEV_DATABASE_PASSWORD}@postgres:5432/ontology"


def _secret_problem(name: str, value: SecretStr, default: str, min_length: int) -> str | None:
    secret = value.get_secret_value()
    if secret == default or len(secret) < min_length:
        return f"{name} must be a non-default value of at least {min_length} characters"
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OP_", env_ignore_empty=True, extra="ignore")

    env: Literal["development", "production"] = "development"
    database_url: str = DEV_DATABASE_URL
    # Server-side secret for encrypting data source credentials and similar secrets (from M3).
    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr(DEV_ADMIN_PASSWORD)
    # Unset means: Secure cookies exactly when env is production. See `secure_cookies`.
    cookie_secure: bool | None = None
    session_idle_hours: int = Field(default=8, gt=0)
    session_absolute_days: int = Field(default=7, gt=0)

    # Model access (M1). AI features report "not configured" while the key is unset.
    openai_api_key: SecretStr | None = None
    # HTTP proxy used only for model calls; may embed credentials, hence secret.
    ai_proxy: SecretStr | None = None
    # OpenAI-compatible endpoint; unset means the official OpenAI API.
    ai_base_url: str | None = None
    ai_model: str = "gpt-6.2-sol"
    ai_reasoning_model: str = "gpt-6.2-astra"
    # Model calls are streamed, so this bounds the wait between two events, not a whole call.
    ai_timeout_seconds: float = Field(default=120, gt=0)

    # Uploaded documents (M1).
    documents_dir: str = "/data/documents"
    max_upload_mb: int = Field(default=20, gt=0)

    @property
    def ai_configured(self) -> bool:
        return self.openai_api_key is not None and bool(self.openai_api_key.get_secret_value())

    @property
    def secure_cookies(self) -> bool:
        return self.env == "production" if self.cookie_secure is None else self.cookie_secure

    @model_validator(mode="after")
    def check_production_values(self) -> Self:
        if self.env != "production":
            return self
        problems = [
            _secret_problem("OP_SECRET_KEY", self.secret_key, DEV_SECRET_KEY, 32),
            _secret_problem("OP_ADMIN_PASSWORD", self.admin_password, DEV_ADMIN_PASSWORD, 12),
        ]
        if DEV_DATABASE_PASSWORD in self.database_url:
            problems.append("OP_DATABASE_URL must not use the development database password")
        found = [problem for problem in problems if problem]
        if found:
            raise ValueError("OP_ENV=production: " + "; ".join(found))
        return self


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
