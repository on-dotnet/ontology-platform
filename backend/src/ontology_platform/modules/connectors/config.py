"""The settings the connector reads when it connects: the credential keys, the statement timeout
and the row limit.

The worker hands its settings over through `configure` (connectors.jobs). The API process reads
them from the OP_* environment, as `create_app()` does: the functions other modules call
(`service.select`, `service.sample_values`) take no settings, and the routes' signatures are fixed
by the M3 skeleton.
"""

from functools import cache

from ontology_platform.settings import Settings

_configured: Settings | None = None


def configure(settings: Settings | None) -> None:
    global _configured
    _configured = settings


def current() -> Settings:
    return _configured if _configured is not None else _from_environment()


@cache
def _from_environment() -> Settings:
    return Settings()
