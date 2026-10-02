"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_users")),
        sa.UniqueConstraint("username", name=op.f("uq_admin_users_username")),
    )
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_tokens_token_hash")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"], unique=False)
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"], unique=False)
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name=op.f("ck_events_window")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("slug", name=op.f("uq_events_slug")),
    )
    op.create_index(
        "uq_events_active",
        "events",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("nickname", sa.String(length=64), nullable=False),
        sa.Column("first_name", sa.String(length=64), nullable=True),
        sa.Column("last_name", sa.String(length=64), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("street", sa.String(length=128), nullable=True),
        sa.Column("postal_code", sa.String(length=16), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("auto_created", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
    )
    op.create_index("ix_players_last_first", "players", ["last_name", "first_name"], unique=False)
    op.create_index(
        "uq_players_nickname_lower",
        "players",
        [sa.literal_column("lower(nickname)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("layout", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), server_default=sa.text("'none'"), nullable=False),
        sa.Column("auto_round", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
            "mode IN ('none', 'top2_advance', 'worst_out', 'winner_only')",
            name=op.f("ck_scenes_mode"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenes")),
        sa.UniqueConstraint("slug", name=op.f("uq_scenes_slug")),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.create_table(
        "stations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stations")),
    )
    op.create_table(
        "event_hidden_stations",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_hidden_stations_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            name=op.f("fk_event_hidden_stations_station_id_stations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", "station_id", name=op.f("pk_event_hidden_stations")),
    )
    op.create_table(
        "event_player_flags",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("hide_everywhere", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "hide_from_bracket", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_player_flags_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_event_player_flags_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", "player_id", name=op.f("pk_event_player_flags")),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("external_id", sa.String(length=96), nullable=True),
        sa.Column("station_id", sa.String(length=64), nullable=True),
        sa.Column("player_id", sa.Integer(), nullable=True),
        sa.Column("card_name", sa.String(length=64), nullable=True),
        sa.Column("card_uid", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'live'"), nullable=False),
        sa.Column(
            "source", sa.String(length=16), server_default=sa.text("'station'"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("active_seconds", sa.Float(), nullable=True),
        sa.Column("end_reason", sa.String(length=16), nullable=True),
        sa.Column("start_level", sa.SmallInteger(), nullable=True),
        sa.Column("end_level", sa.SmallInteger(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("lines", sa.Integer(), nullable=True),
        sa.Column("clears_single", sa.Integer(), nullable=True),
        sa.Column("clears_double", sa.Integer(), nullable=True),
        sa.Column("clears_triple", sa.Integer(), nullable=True),
        sa.Column("clears_tetris", sa.Integer(), nullable=True),
        sa.Column("tetris_rate", sa.Float(), nullable=True),
        sa.Column("burn", sa.Integer(), nullable=True),
        sa.Column("max_drought", sa.Integer(), nullable=True),
        sa.Column("pieces", sa.Integer(), nullable=True),
        sa.Column("pps", sa.Float(), nullable=True),
        sa.Column("cheated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cheat_points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=True),
        sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_end", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "end_reason IS NULL OR end_reason IN ('game_over', 'reset', 'signal_lost', 'shutdown')",
            name=op.f("ck_games_end_reason"),
        ),
        sa.CheckConstraint(
            "source IN ('station', 'manual', 'ngf_import')", name=op.f("ck_games_source")
        ),
        sa.CheckConstraint(
            "status IN ('live', 'finished', 'abandoned')", name=op.f("ck_games_status")
        ),
        sa.CheckConstraint("score IS NULL OR score >= 0", name=op.f("ck_games_score")),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_games_player_id_players"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            name=op.f("fk_games_station_id_stations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
        sa.UniqueConstraint("external_id", name=op.f("uq_games_external_id")),
    )
    op.create_index(
        "ix_games_player_score",
        "games",
        ["player_id", sa.literal_column("score DESC")],
        unique=False,
    )
    op.create_index("ix_games_started_at", "games", ["started_at"], unique=False)
    op.create_index("ix_games_station_id", "games", ["station_id"], unique=False)
    op.create_table(
        "scene_rounds",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_scene_rounds_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scene_rounds")),
        sa.UniqueConstraint("scene_id", "number", name="uq_scene_rounds_scene_number"),
    )
    op.create_table(
        "scene_slots",
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=True),
        sa.Column("label_override", sa.String(length=64), nullable=True),
        sa.Column("name_override", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_scene_slots_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            name=op.f("fk_scene_slots_station_id_stations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("scene_id", "slot", name=op.f("pk_scene_slots")),
    )
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active_count", sa.SmallInteger(), server_default=sa.text("16"), nullable=False),
        sa.Column("is_seeded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "seeds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "winners",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=True),
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
            "active_count BETWEEN 2 AND 64", name=op.f("ck_tournaments_active_count")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_tournaments_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tournaments")),
    )
    op.create_index(op.f("ix_tournaments_event_id"), "tournaments", ["event_id"], unique=False)
    op.create_table(
        "event_hidden_games",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_hidden_games_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name=op.f("fk_event_hidden_games_game_id_games"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", "game_id", name=op.f("pk_event_hidden_games")),
    )
    op.create_table(
        "game_cheats",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cheated", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("score_before", sa.Integer(), nullable=False),
        sa.Column("score_after", sa.Integer(), nullable=False),
        sa.Column("lines_delta", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_game_cheats_game_id_games"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_cheats")),
        sa.UniqueConstraint("game_id", "ts", name="uq_game_cheats_game_ts"),
    )
    op.create_table(
        "game_frames",
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("t_ms", sa.Integer(), nullable=False),
        sa.Column("game_state", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("lines", sa.Integer(), nullable=True),
        sa.Column("level", sa.SmallInteger(), nullable=True),
        sa.Column("next_piece", sa.String(length=1), nullable=True),
        sa.Column("playfield", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_game_frames_game_id_games"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("game_id", "seq", name=op.f("pk_game_frames")),
    )
    op.create_table(
        "game_recordings",
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("ngf_gz", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name=op.f("fk_game_recordings_game_id_games"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("game_id", name=op.f("pk_game_recordings")),
    )
    op.create_table(
        "scene_round_entries",
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=True),
        sa.Column("frozen_score", sa.Integer(), nullable=True),
        sa.Column("frozen_lines", sa.Integer(), nullable=True),
        sa.Column("frozen_level", sa.SmallInteger(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('advanced', 'eliminated', 'winner')",
            name=op.f("ck_scene_round_entries_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name=op.f("fk_scene_round_entries_game_id_games"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["scene_rounds.id"],
            name=op.f("fk_scene_round_entries_round_id_scene_rounds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("round_id", "slot", name=op.f("pk_scene_round_entries")),
    )


def downgrade() -> None:
    op.drop_table("scene_round_entries")
    op.drop_table("game_recordings")
    op.drop_table("game_frames")
    op.drop_table("game_cheats")
    op.drop_table("event_hidden_games")
    op.drop_index(op.f("ix_tournaments_event_id"), table_name="tournaments")
    op.drop_table("tournaments")
    op.drop_table("scene_slots")
    op.drop_table("scene_rounds")
    op.drop_index("ix_games_station_id", table_name="games")
    op.drop_index("ix_games_started_at", table_name="games")
    op.drop_index("ix_games_player_score", table_name="games")
    op.drop_table("games")
    op.drop_table("event_player_flags")
    op.drop_table("event_hidden_stations")
    op.drop_table("stations")
    op.drop_table("settings")
    op.drop_table("scenes")
    op.drop_index(
        "uq_players_nickname_lower",
        table_name="players",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_players_last_first", table_name="players")
    op.drop_table("players")
    op.drop_index("uq_events_active", table_name="events", postgresql_where=sa.text("is_active"))
    op.drop_table("events")
    op.drop_index("ix_audit_log_ts", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("api_tokens")
    op.drop_table("admin_users")
