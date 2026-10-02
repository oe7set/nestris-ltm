"""player cards

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_cards",
        sa.Column("uid", sa.String(length=32), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("card_name", sa.String(length=64), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_cards_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", name=op.f("pk_player_cards")),
    )
    op.create_index(op.f("ix_player_cards_player_id"), "player_cards", ["player_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_player_cards_player_id"), table_name="player_cards")
    op.drop_table("player_cards")
