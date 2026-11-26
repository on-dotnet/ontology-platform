"""Imports every module's tables so that they are registered on Base.metadata.

Alembic, the migration tests and the worker import this module instead of listing modules
one by one. Add new modules here.
"""

from ontology_platform.modules.ai import models as ai_models
from ontology_platform.modules.audit import models as audit_models
from ontology_platform.modules.connectors import models as connectors_models
from ontology_platform.modules.cq import models as cq_models
from ontology_platform.modules.documents import models as documents_models
from ontology_platform.modules.identity import models as identity_models
from ontology_platform.modules.jobs import models as jobs_models
from ontology_platform.modules.ontology import models as ontology_models

__all__ = [
    "ai_models",
    "audit_models",
    "connectors_models",
    "cq_models",
    "documents_models",
    "identity_models",
    "jobs_models",
    "ontology_models",
]
