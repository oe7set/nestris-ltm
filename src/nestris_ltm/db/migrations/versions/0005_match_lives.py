"""match lives: hearts per 1-vs-1 match, scene pair bindings

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("default_lives", sa.SmallInteger(), server_default=sa.text("2"), nullable=False),
    )
    op.add_column(
        "tournaments",
        sa.Column("auto_bind", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "tournaments",
        sa.Column("auto_deduct", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.create_table(
        "match_series",
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.String(length=16), nullable=False),
        sa.Column("max_lives", sa.SmallInteger(), nullable=True),
        sa.Column(
            "decided_by_lives", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_lives IS NULL OR max_lives BETWEEN 1 AND 9", name=op.f("ck_match_series_max_lives")
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_match_series_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tournament_id", "match_id", name=op.f("pk_match_series")),
    )

    op.create_table(
        "match_life_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.String(length=16), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("value", sa.SmallInteger(), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=True),
        sa.Column("scene_slug", sa.String(length=64), nullable=True),
        sa.Column("scene_round", sa.Integer(), nullable=True),
        sa.Column("pair", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('lose', 'gain', 'set')", name=op.f("ck_match_life_events_kind")
        ),
        sa.CheckConstraint(
            "source IN ('admin', 'api', 'auto')", name=op.f("ck_match_life_events_source")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_match_life_events_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_match_life_events_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_life_events")),
    )
    op.create_index(
        "ix_match_life_events_match",
        "match_life_events",
        ["tournament_id", "match_id", "id"],
        unique=False,
    )
    op.create_index(
        "uq_match_life_events_auto",
        "match_life_events",
        ["tournament_id", "scene_slug", "scene_round", "pair"],
        unique=True,
        postgresql_where=sa.text("source = 'auto' AND undone_at IS NULL"),
    )

    op.create_table(
        "scene_pair_matches",
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("pair", sa.SmallInteger(), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.String(length=16), nullable=False),
        sa.Column("bound_by", sa.String(length=8), nullable=False),
        sa.Column(
            "bound_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "bound_by IN ('manual', 'auto')", name=op.f("ck_scene_pair_matches_bound_by")
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_scene_pair_matches_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_scene_pair_matches_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("scene_id", "pair", name=op.f("pk_scene_pair_matches")),
    )


def downgrade() -> None:
    op.drop_table("scene_pair_matches")
    op.drop_index("uq_match_life_events_auto", table_name="match_life_events")
    op.drop_index("ix_match_life_events_match", table_name="match_life_events")
    op.drop_table("match_life_events")
    op.drop_table("match_series")
    op.drop_column("tournaments", "auto_deduct")
    op.drop_column("tournaments", "auto_bind")
    op.drop_column("tournaments", "default_lives")
