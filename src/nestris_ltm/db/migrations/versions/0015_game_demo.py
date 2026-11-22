"""games flagged as attract-mode demos

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("games", sa.Column("demo_reason", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_games_is_demo"), "games", ["is_demo"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_games_is_demo"), table_name="games")
    op.drop_column("games", "demo_reason")
    op.drop_column("games", "is_demo")
