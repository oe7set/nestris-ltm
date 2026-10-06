"""scene flow (phase | quali | rounds) replaces auto_round + qualifying

The next-round behaviour becomes one global setting (``scenes.next_round``),
``auto`` when any scene started its rounds automatically before.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scenes",
        sa.Column("flow", sa.String(length=8), server_default=sa.text("'phase'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_scenes_flow"), "scenes", "flow IN ('phase', 'quali', 'rounds')"
    )
    op.execute("UPDATE scenes SET flow = 'quali' WHERE qualifying")
    op.execute(
        """
        INSERT INTO settings (key, value)
        SELECT 'scenes.next_round',
               jsonb_build_object('next_round',
                   CASE WHEN EXISTS (SELECT 1 FROM scenes WHERE auto_round)
                        THEN 'auto' ELSE 'manual' END)
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.drop_column("scenes", "qualifying")
    op.drop_column("scenes", "auto_round")


def downgrade() -> None:
    op.add_column(
        "scenes",
        sa.Column("auto_round", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "scenes",
        sa.Column("qualifying", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute("UPDATE scenes SET qualifying = (flow = 'quali')")
    op.execute(
        "UPDATE scenes SET auto_round = EXISTS (SELECT 1 FROM settings"
        " WHERE key = 'scenes.next_round' AND value->>'next_round' = 'auto')"
    )
    op.execute("DELETE FROM settings WHERE key = 'scenes.next_round'")
    op.drop_constraint(op.f("ck_scenes_flow"), "scenes", type_="check")
    op.drop_column("scenes", "flow")
