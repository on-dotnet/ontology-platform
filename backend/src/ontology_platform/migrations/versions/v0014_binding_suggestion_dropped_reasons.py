"""Store counts by reason for dropped binding suggestions.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "binding_suggestions", sa.Column("dropped_reasons", JSONB(), nullable=True), schema="ai"
    )


def downgrade() -> None:
    op.drop_column("binding_suggestions", "dropped_reasons", schema="ai")
