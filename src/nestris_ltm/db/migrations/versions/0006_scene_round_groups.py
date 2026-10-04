"""scene rounds per group: every head-to-head pair plays its own rounds

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scene_rounds",
        sa.Column("group_index", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.drop_constraint("uq_scene_rounds_scene_number", "scene_rounds", type_="unique")
    op.create_unique_constraint(
        "uq_scene_rounds_scene_group_number", "scene_rounds", ["scene_id", "group_index", "number"]
    )


def downgrade() -> None:
    # Only group 0 fits the old constraint.
    op.execute("DELETE FROM scene_rounds WHERE group_index <> 0")
    op.drop_constraint("uq_scene_rounds_scene_group_number", "scene_rounds", type_="unique")
    op.create_unique_constraint(
        "uq_scene_rounds_scene_number", "scene_rounds", ["scene_id", "number"]
    )
    op.drop_column("scene_rounds", "group_index")
