"""SQLAlchemy ORM models: the complete NestrisLTM schema.

Schema changes go through Alembic (``db/migrations``); never edit an applied
revision. Enumerations are stored as short strings guarded by CHECK
constraints, which keeps migrations simple compared to native PG enums.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

GAME_STATUSES = ("live", "finished", "abandoned")
GAME_SOURCES = ("station", "manual", "ngf_import")
END_REASONS = ("game_over", "reset", "signal_lost", "shutdown")
SCENE_MODES = ("none", "top2_advance", "worst_out", "winner_only")
ROUND_OUTCOMES = ("advanced", "eliminated", "winner")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------- events


class Event(TimestampMixin, Base):
    """A tournament edition. The active event's window scopes every view."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="window"),
        # At most one active event.
        Index(
            "uq_events_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


# ---------------------------------------------------------------- players


class Player(TimestampMixin, Base):
    __tablename__ = "players"
    __table_args__ = (
        # Case-insensitive unique nickname among non-deleted players.
        Index(
            "uq_players_nickname_lower",
            func.lower(text("nickname")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_players_last_first", "last_name", "first_name"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    birth_date: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    street: Mapped[str | None] = mapped_column(String(128))
    postal_code: Mapped[str | None] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    # Created by the ingest from an unknown card name.
    auto_created: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None]


class PlayerCard(Base):
    """An RFID card UID learned for a player. A player may own several cards."""

    __tablename__ = "player_cards"

    uid: Mapped[str] = mapped_column(String(32), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    # Name written on the card when it was first seen.
    card_name: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- stations


class Station(Base):
    """A capture station; created on its first MQTT message."""

    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    last_seen_at: Mapped[datetime | None]
    last_status: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- games


class Game(TimestampMixin, Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(_in("status", GAME_STATUSES), name="status"),
        CheckConstraint(_in("source", GAME_SOURCES), name="source"),
        CheckConstraint(
            f"end_reason IS NULL OR {_in('end_reason', END_REASONS)}", name="end_reason"
        ),
        CheckConstraint("score IS NULL OR score >= 0", name="score"),
        Index("ix_games_started_at", "started_at"),
        Index("ix_games_player_score", "player_id", text("score DESC")),
        Index("ix_games_station_id", "station_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # The station's game_id; NULL for manual entries. Unique: MQTT delivery is
    # at-least-once, so every write is an upsert on this key.
    external_id: Mapped[str | None] = mapped_column(String(96), unique=True)
    station_id: Mapped[str | None] = mapped_column(ForeignKey("stations.id", ondelete="SET NULL"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"))
    # What the RFID card said, kept for later re-assignment.
    card_name: Mapped[str | None] = mapped_column(String(64))
    card_uid: Mapped[str | None] = mapped_column(String(32))

    status: Mapped[str] = mapped_column(String(16), server_default=text("'live'"))
    source: Mapped[str] = mapped_column(String(16), server_default=text("'station'"))

    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    duration_s: Mapped[float | None] = mapped_column(Float)
    active_seconds: Mapped[float | None] = mapped_column(Float)
    end_reason: Mapped[str | None] = mapped_column(String(16))

    start_level: Mapped[int | None] = mapped_column(SmallInteger)
    end_level: Mapped[int | None] = mapped_column(SmallInteger)
    score: Mapped[int | None] = mapped_column(Integer)
    lines: Mapped[int | None] = mapped_column(Integer)
    clears_single: Mapped[int | None] = mapped_column(Integer)
    clears_double: Mapped[int | None] = mapped_column(Integer)
    clears_triple: Mapped[int | None] = mapped_column(Integer)
    clears_tetris: Mapped[int | None] = mapped_column(Integer)
    tetris_rate: Mapped[float | None] = mapped_column(Float)
    burn: Mapped[int | None] = mapped_column(Integer)
    max_drought: Mapped[int | None] = mapped_column(Integer)
    pieces: Mapped[int | None] = mapped_column(Integer)
    pps: Mapped[float | None] = mapped_column(Float)

    cheated: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cheat_points: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # NULL until the station reported a validation (manual games stay NULL).
    valid: Mapped[bool | None] = mapped_column(Boolean)
    validation: Mapped[dict[str, Any] | None]
    raw_end: Mapped[dict[str, Any] | None]

    is_edited: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)

    player: Mapped[Player | None] = relationship(lazy="raise")
    station: Mapped[Station | None] = relationship(lazy="raise")


class GameFrame(Base):
    """A live frame received over MQTT (at most ``live_max_hz`` per game)."""

    __tablename__ = "game_frames"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Milliseconds since the game started.
    t_ms: Mapped[int] = mapped_column(Integer)
    game_state: Mapped[str] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer)
    lines: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[int | None] = mapped_column(SmallInteger)
    next_piece: Mapped[str | None] = mapped_column(String(1))
    # 200 cells x 2 bits, NGF layout; NULL while paused.
    playfield: Mapped[bytes | None] = mapped_column(LargeBinary)


class GameRecording(Base):
    """The station's complete NestrisChamps recording (``.ngf.gz``)."""

    __tablename__ = "game_recordings"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    ngf_gz: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    frame_count: Mapped[int | None] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


class GameCheat(Base):
    __tablename__ = "game_cheats"
    __table_args__ = (UniqueConstraint("game_id", "ts", name="uq_game_cheats_game_ts"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    ts: Mapped[datetime]
    cheated: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    score_before: Mapped[int] = mapped_column(Integer)
    score_after: Mapped[int] = mapped_column(Integer)
    lines_delta: Mapped[int] = mapped_column(Integer)


# ---------------------------------------------------------------- per-event visibility


class EventPlayerFlags(Base):
    __tablename__ = "event_player_flags"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    hide_everywhere: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    hide_from_bracket: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class EventHiddenStation(Base):
    __tablename__ = "event_hidden_stations"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    station_id: Mapped[str] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True
    )


class EventHiddenGame(Base):
    __tablename__ = "event_hidden_games"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str | None] = mapped_column(String(255))


# ---------------------------------------------------------------- tournament


class Tournament(TimestampMixin, Base):
    """Single-elimination bracket state (ported from TournamentHigscore)."""

    __tablename__ = "tournaments"
    __table_args__ = (CheckConstraint("active_count BETWEEN 2 AND 64", name="active_count"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    active_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("16"))
    is_seeded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # List of seeded player snapshots (or null for an empty seed).
    seeds: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    # {match_id: player_id}
    winners: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    seeded_at: Mapped[datetime | None]


# ---------------------------------------------------------------- scenes (OBS overlays)


class Scene(TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (CheckConstraint(_in("mode", SCENE_MODES), name="mode"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    layout: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16), server_default=text("'none'"))
    auto_round: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class SceneSlot(Base):
    __tablename__ = "scene_slots"

    scene_id: Mapped[int] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    station_id: Mapped[str | None] = mapped_column(ForeignKey("stations.id", ondelete="SET NULL"))
    label_override: Mapped[str | None] = mapped_column(String(64))
    name_override: Mapped[str | None] = mapped_column(String(64))


class SceneRound(Base):
    __tablename__ = "scene_rounds"
    __table_args__ = (UniqueConstraint("scene_id", "number", name="uq_scene_rounds_scene_number"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]


class SceneRoundEntry(Base):
    """One slot in a round; the frozen values keep a finished score on screen."""

    __tablename__ = "scene_round_entries"
    __table_args__ = (
        CheckConstraint(f"outcome IS NULL OR {_in('outcome', ROUND_OUTCOMES)}", name="outcome"),
    )

    round_id: Mapped[int] = mapped_column(
        ForeignKey("scene_rounds.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"))
    frozen_score: Mapped[int | None] = mapped_column(Integer)
    frozen_lines: Mapped[int | None] = mapped_column(Integer)
    frozen_level: Mapped[int | None] = mapped_column(SmallInteger)
    finished_at: Mapped[datetime | None]
    outcome: Mapped[str | None] = mapped_column(String(16))


# ---------------------------------------------------------------- auth, settings, audit


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]


class ApiToken(Base):
    """Bearer tokens for machine clients (registration kiosk, stations)."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    # SHA-256 of the token; the token itself is shown once and never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class Setting(Base):
    """Runtime settings edited in the admin UI (key -> JSON value)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity", "entity_id"),
        Index("ix_audit_log_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ts: Mapped[datetime] = mapped_column(server_default=func.now())
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
