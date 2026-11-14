"""overlay layouts remember the template they came from

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("overlay_layouts", sa.Column("template_id", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("overlay_layouts", "template_id")
