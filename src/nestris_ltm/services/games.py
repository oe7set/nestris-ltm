"""Game writes coming from the station ingest.

Every write is idempotent: MQTT delivery is at-least-once and events can
arrive out of order (a spooled ``game_end`` may come before ``game_start``),
so all writes are upserts keyed on the station's ``game_id``
(``games.external_id``). Games edited by the crew (``is_edited``) are never
overwritten by a re-delivered event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Game, GameCheat, Station
from nestris_ltm.ingest.payloads import CheatPayload, GameEndPayload, GameStartPayload
from nestris_ltm.services.players import resolve_card


async def ensure_station(session: AsyncSession, station_id: str) -> None:
    await session.execute(
        insert(Station).values(id=station_id).on_conflict_do_nothing(index_elements=[Station.id])
    )


async def _card_player(
    session: AsyncSession, payload: GameStartPayload | GameEndPayload | CheatPayload
) -> tuple[int | None, str | None, str | None]:
    card = payload.player
    if card is None:
        return None, None, None
    player_id = await resolve_card(session, card.uid, card.name)
    return player_id, card.name, card.uid


async def record_game_start(session: AsyncSession, payload: GameStartPayload) -> int:
    """Create the game as ``live``; a no-op if it already exists. Returns its id."""
    await ensure_station(session, payload.station)
    player_id, card_name, card_uid = await _card_player(session, payload)
    await session.execute(
        insert(Game)
        .values(
            external_id=payload.game_id,
            station_id=payload.station,
            player_id=player_id,
            card_name=card_name,
            card_uid=card_uid,
            status="live",
            source="station",
            started_at=payload.started_at,
            start_level=payload.start_level,
        )
        .on_conflict_do_nothing(index_elements=[Game.external_id])
    )
    # A station runs one game at a time: earlier games still marked live
    # never got their game_end (power cut, crash) and are closed now.
    await session.execute(
        update(Game)
        .where(
            Game.station_id == payload.station,
            Game.status == "live",
            Game.external_id != payload.game_id,
            Game.started_at < payload.started_at,
        )
        .values(status="abandoned", updated_at=func.now())
    )
    return await _game_id(session, payload.game_id)


async def record_game_end(session: AsyncSession, payload: GameEndPayload) -> int:
    """Finalize the game (creating it if ``game_start`` never arrived)."""
    await ensure_station(session, payload.station)
    player_id, card_name, card_uid = await _card_player(session, payload)
    values = {
        "station_id": payload.station,
        "player_id": player_id,
        "card_name": card_name,
        "card_uid": card_uid,
        "status": "finished",
        "source": "station",
        "started_at": payload.started_at,
        "ended_at": payload.ended_at,
        "duration_s": payload.duration_s,
        "active_seconds": payload.active_seconds,
        "end_reason": payload.end_reason,
        "start_level": payload.start_level,
        "end_level": payload.end_level,
        "score": payload.score,
        "lines": payload.lines,
        "clears_single": payload.clears.single,
        "clears_double": payload.clears.double,
        "clears_triple": payload.clears.triple,
        "clears_tetris": payload.clears.tetris,
        "tetris_rate": payload.tetris_rate,
        "burn": payload.burn,
        "max_drought": payload.max_drought,
        "pieces": payload.pieces,
        "pps": payload.pps,
        "cheated": payload.cheated,
        "cheat_points": payload.cheat_points,
        "valid": payload.valid,
        "validation": payload.validation.model_dump(),
        "raw_end": payload.model_dump(mode="json", by_alias=True),
    }
    stmt = insert(Game).values(external_id=payload.game_id, **values)
    update_set: dict[str, Any] = {
        k: stmt.excluded[k] for k in values if k not in ("player_id", "source")
    }
    # Keep a player assigned earlier (game_start or the crew); fill it if missing.
    update_set["player_id"] = func.coalesce(Game.player_id, stmt.excluded.player_id)
    update_set["updated_at"] = func.now()
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[Game.external_id],
            set_=update_set,
            where=Game.is_edited.is_(False),
        )
    )
    return await _game_id(session, payload.game_id)


async def record_cheat(session: AsyncSession, payload: CheatPayload) -> int:
    """Store a cheat detection; the game row is created if it is still missing."""
    game_id = await _game_id_or_none(session, payload.game_id)
    if game_id is None:
        # Cheat before game_start (out-of-order delivery): create a stub game.
        game_id = await record_game_start(
            session,
            GameStartPayload(
                game_id=payload.game_id,
                station=payload.station,
                player=payload.player,
                started_at=payload.ts,
            ),
        )
    await session.execute(
        insert(GameCheat)
        .values(
            game_id=game_id,
            ts=payload.ts,
            cheated=payload.cheated,
            count=payload.count,
            points=payload.points,
            score_before=payload.score_before,
            score_after=payload.score_after,
            lines_delta=payload.lines_delta,
        )
        .on_conflict_do_nothing(constraint="uq_game_cheats_game_ts")
    )
    await session.execute(
        update(Game)
        .where(Game.id == game_id, Game.status == "live", Game.is_edited.is_(False))
        .values(cheated=func.greatest(Game.cheated, payload.cheated), updated_at=func.now())
    )
    return game_id


async def abandon_stale_games(session: AsyncSession, older_than: timedelta) -> int:
    """Mark live games that never received a ``game_end`` as abandoned."""
    cutoff = datetime.now(UTC) - older_than
    result = await session.execute(
        update(Game)
        .where(and_(Game.status == "live", Game.started_at < cutoff))
        .values(status="abandoned", updated_at=func.now())
    )
    return result.rowcount or 0  # type: ignore[attr-defined]


async def _game_id_or_none(session: AsyncSession, external_id: str) -> int | None:
    result = await session.execute(select(Game.id).where(Game.external_id == external_id))
    return result.scalar_one_or_none()


async def _game_id(session: AsyncSession, external_id: str) -> int:
    game_id = await _game_id_or_none(session, external_id)
    if game_id is None:  # pragma: no cover - the upsert above guarantees the row
        raise LookupError(external_id)
    return game_id
