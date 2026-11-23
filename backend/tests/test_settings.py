"""Production refuses development defaults and weak secrets; cookies default to Secure there."""

import pytest
from pydantic import SecretStr, ValidationError

from ontology_platform.main import create_app
from ontology_platform.settings import (
    DEV_ADMIN_PASSWORD,
    DEV_DATABASE_URL,
    DEV_SECRET_KEY,
    Settings,
)

PRODUCTION_DATABASE = "postgresql+psycopg://ontology:a-real-password@db:5432/ontology"
STRONG_SECRET = "s" * 32
STRONG_PASSWORD = "p" * 12


def production(
    secret_key: str = STRONG_SECRET,
    admin_password: str = STRONG_PASSWORD,
    database_url: str = PRODUCTION_DATABASE,
) -> Settings:
    return Settings(
        env="production",
        secret_key=SecretStr(secret_key),
        admin_password=SecretStr(admin_password),
        database_url=database_url,
    )


@pytest.mark.parametrize(
    ("overrides", "rejected"),
    [
        ({"secret_key": DEV_SECRET_KEY}, "OP_SECRET_KEY"),
        ({"secret_key": "s" * 31}, "OP_SECRET_KEY"),
        ({"admin_password": DEV_ADMIN_PASSWORD}, "OP_ADMIN_PASSWORD"),
        ({"admin_password": "p" * 11}, "OP_ADMIN_PASSWORD"),
        ({"database_url": DEV_DATABASE_URL}, "OP_DATABASE_URL"),
    ],
)
def test_production_rejects_weak_values(overrides: dict[str, str], rejected: str) -> None:
    with pytest.raises(ValidationError, match=rejected):
        production(**overrides)


def test_production_accepts_strong_values_and_hides_docs() -> None:
    settings = production()

    app = create_app(settings)

    assert settings.secure_cookies is True
    assert app.openapi_url is None
    assert app.docs_url is None


def test_app_refuses_to_start_with_default_values_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OP_ENV", "production")
    for name in ("OP_SECRET_KEY", "OP_ADMIN_PASSWORD", "OP_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as caught:
        create_app()

    for name in ("OP_SECRET_KEY", "OP_ADMIN_PASSWORD", "OP_DATABASE_URL"):
        assert name in str(caught.value)


def test_secure_cookies_follow_env_unless_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_COOKIE_SECURE", "")

    assert Settings().cookie_secure is None
    assert Settings().secure_cookies is False
    assert production().secure_cookies is True
    assert Settings(cookie_secure=True).secure_cookies is True
