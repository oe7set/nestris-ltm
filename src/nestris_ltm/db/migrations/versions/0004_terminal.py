"""terminal: e-mail consent, self-reported games

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "source IN ('station', 'manual', 'ngf_import')"
NEW = "source IN ('station', 'manual', 'ngf_import', 'self_reported')"


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("email_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "players", sa.Column("email_consent_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Autogenerate does not see CHECK changes: recreate the constraint.
    op.drop_constraint(op.f("ck_games_source"), "games", type_="check")
    op.create_check_constraint(op.f("ck_games_source"), "games", NEW)


def downgrade() -> None:
    op.execute("DELETE FROM games WHERE source = 'self_reported'")
    op.drop_constraint(op.f("ck_games_source"), "games", type_="check")
    op.create_check_constraint(op.f("ck_games_source"), "games", OLD)
    op.drop_column("players", "email_consent_at")
    op.drop_column("players", "email_consent")
