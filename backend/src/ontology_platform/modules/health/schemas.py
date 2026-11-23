"""Health API models."""

from typing import Literal

from ontology_platform.schemas import CamelModel


class HealthStatus(CamelModel):
    status: Literal["ok"] = "ok"
