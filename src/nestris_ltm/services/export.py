"""CSV exports and the results of an event (highscore, podium).

CSV files use ";" and a UTF-8 byte order mark, so a German Excel opens
them with umlauts and columns right; LibreOffice and scripts read them too.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Event, Player
from nestris_ltm.services import events, highscore

if TYPE_CHECKING:
    from nestris_ltm.runtime import Runtime

ALL_PLAYERS = 100_000


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else _cell(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float):
        return f"{value:.3f}".replace(".", ",")
    return value


def filename(kind: str, event: Event | None) -> str:
    scope = event.slug if event is not None else "alle"
    return f"nestrisltm-{scope}-{kind}-{datetime.now():%Y%m%d-%H%M}.csv"


async def results(rt: Runtime, session: AsyncSession) -> dict[str, Any]:
    """The active event's highscore (all players) and, once fixed, the podium."""
    event = await events.active_event(session)
    standings = await highscore.compute_standings(
        session, event, {}, display_count=ALL_PLAYERS, pool_size=1
    )
    podium = None
    if rt.tournament.seeded():
        bracket = rt.tournament.state.bracket()
        if bracket.rounds:
            podium = {
                place: (p.nickname if p is not None else None)
                for place, p in (
                    ("champion", bracket.champion),
                    ("runner_up", bracket.runner_up),
                    ("third", bracket.third_place),
                )
            }
    event_info = None
    if event is not None:
        event_info = {
            "id": event.id,
            "name": event.name,
            "slug": event.slug,
            "starts_at": event.starts_at.isoformat(),
            "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        }
    return {
        "event": event_info,
        "leaderboard": [e.model_dump(mode="json") for e in standings.leaderboard],
        "stats": standings.stats.model_dump(mode="json"),
        "podium": podium,
    }


async def highscore_csv(session: AsyncSession) -> tuple[bytes, Event | None]:
    event = await events.active_event(session)
    standings = await highscore.compute_standings(
        session, event, {}, display_count=ALL_PLAYERS, pool_size=1
    )
    rows = (
        (e.rank, e.nickname, e.score, e.lines, e.level, e.tetris_rate, e.game_id)
        for e in standings.leaderboard
    )
    header = ("Rang", "Spieler", "Score", "Lines", "Level", "Tetris-Rate", "Spiel-ID")
    return to_csv(header, rows), event


async def players_csv(session: AsyncSession, *, contact: bool) -> bytes:
    players = (
        await session.scalars(
            select(Player).where(Player.deleted_at.is_(None)).order_by(Player.nickname)
        )
    ).all()
    header = ["ID", "Nickname", "Vorname", "Nachname", "Angelegt"]
    if contact:
        header += ["Geburtsdatum", "E-Mail", "Telefon", "Straße", "PLZ", "Ort", "Land"]
    rows = []
    for p in players:
        row: list[Any] = [p.id, p.nickname, p.first_name, p.last_name, p.created_at]
        if contact:
            row += [p.birth_date, p.email, p.phone, p.street, p.postal_code, p.city, p.country]
        rows.append(row)
    return to_csv(header, rows)


GAME_HEADER = (
    "ID", "Start", "Ende", "Spieler", "Karte", "Station", "Status", "Quelle", "Score", "Lines",
    "Start-Level", "End-Level", "Tetris-Rate", "Dauer (s)", "Cheat", "Gültig", "Bearbeitet",
)  # fmt: skip


def game_rows(rows: Iterable[Any]) -> Iterable[Sequence[Any]]:
    for game, nickname in rows:
        yield (
            game.id, game.started_at, game.ended_at, nickname, game.card_name, game.station_id,
            game.status, game.source, game.score, game.lines, game.start_level, game.end_level,
            game.tetris_rate, game.duration_s, game.cheated or "",
            "" if game.valid is None else ("ja" if game.valid else "nein"),
            "ja" if game.is_edited else "",
        )  # fmt: skip
