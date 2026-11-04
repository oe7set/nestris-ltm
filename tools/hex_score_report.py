"""Report games whose score was stored as a base-16 reading. Reads only.

nestris-core up to 0.3.0 could read SCORE as a base-16 number: the screen's
025782 was stored as 153474. This lists the finished station games where the
stored score is impossible for their clears while the digits it came from fit
them, with the corrected value. It changes nothing.

    uv run python tools/hex_score_report.py [--config <file>]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from nestris_ltm.config import load_settings
from nestris_ltm.db.models import Game

SOFTDROP_PER_PIECE = 40
TOLERANCE = 1_000


def screen_score(stored: int) -> int | None:
    """The decimal score behind a base-16 reading (None: not such a reading)."""
    digits = f"{stored:X}"
    return int(digits) if digits.isdigit() else None


def clear_points(game: Game) -> int:
    return (
        (game.clears_single or 0) * 40
        + (game.clears_double or 0) * 100
        + (game.clears_triple or 0) * 300
        + (game.clears_tetris or 0) * 1200
    )


def legal_range(game: Game) -> tuple[int, int]:
    """Lowest and highest score the game's clears allow."""
    base = clear_points(game)
    low = base * ((game.start_level or 0) + 1)
    high = base * ((game.end_level or game.start_level or 0) + 1)
    return low, high + (game.pieces or 0) * SOFTDROP_PER_PIECE + TOLERANCE


def corrected(game: Game) -> int | None:
    """The real score of a game stored as a base-16 reading, else None."""
    if game.score is None:
        return None
    low, high = legal_range(game)
    fixed = screen_score(game.score)
    if game.score <= high or fixed is None or fixed == game.score:
        return None
    return fixed if low - TOLERANCE <= fixed <= high else None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    engine = create_async_engine(load_settings(args.config).database.url())
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        rows = (
            await conn.execute(
                select(Game).where(Game.status == "finished", Game.source == "station")
            )
        ).all()
    await engine.dispose()

    affected = 0
    print("id\tgestartet\tstation\tlevel\tlines\tgespeichert\tkorrigiert\tvalid\tcheated")
    for game in rows:
        fixed = corrected(game)
        if fixed is None:
            continue
        affected += 1
        print(
            f"{game.id}\t{game.started_at:%Y-%m-%d %H:%M}\t{game.station_id}\t"
            f"{game.start_level}-{game.end_level}\t{game.lines}\t{game.score}\t{fixed}\t"
            f"{game.valid}\t{game.cheated}"
        )
    print(f"\n{affected} von {len(rows)} Spielen betroffen. Es wurde nichts geändert.")


if __name__ == "__main__":
    asyncio.run(main())
