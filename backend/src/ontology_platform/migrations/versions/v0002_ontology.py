"""Ontology working version, change sets and releases (owner: ontology module).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from collections.abc import Sequence

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
