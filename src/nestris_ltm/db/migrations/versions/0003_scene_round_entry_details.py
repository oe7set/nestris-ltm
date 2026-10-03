"""scene round entry details

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scene_round_entries", sa.Column("game_external_id", sa.String(length=96), nullable=True)
    )
    op.add_column(
        "scene_round_entries", sa.Column("player_name", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "scene_round_entries", sa.Column("frozen_start_level", sa.SmallInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("scene_round_entries", "frozen_start_level")
    op.drop_column("scene_round_entries", "player_name")
    op.drop_column("scene_round_entries", "game_external_id")
