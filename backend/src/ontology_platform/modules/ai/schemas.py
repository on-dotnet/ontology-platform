"""API models of the ai module."""

from ontology_platform.schemas import CamelModel


class AiStatus(CamelModel):
    configured: bool
    reachable: bool | None
    model: str | None
