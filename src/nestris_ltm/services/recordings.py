"""Game recordings (NestrisChamps NGF).

- A station uploads the complete ``.ngf.gz`` of a game after it ended. It is
  validated (decoded), stored in ``game_recordings`` and the game's live
  frames are deleted: the recording is complete (every NES frame) and far
  smaller than the 60 Hz live rows.
- Every game can be replayed in one format: its stored recording, or, while
  none exists, an NGF synthesized from the live frames.
- NGF files can be imported as new games (e.g. recordings made elsewhere).
"""

from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import playfield
from nestris_ltm.core.ngf import NgfError, NgfFrame, encode_file, iter_frames, split_games
from nestris_ltm.core.ngf_stats import GameTracker
from nestris_ltm.db.models import Game, GameFrame, GameRecording

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MIN_IMPORT_FRAMES = 60


class RecordingError(ValueError):
    """The upload is not a usable NGF recording."""


@dataclass(frozen=True, slots=True)
class StoredRecording:
    game_id: int
    size_bytes: int
    sha256: str
    frame_count: int
    created: bool  # False when the identical file was stored already
    frames_pruned: int


def decode(data: bytes) -> list[NgfFrame]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise RecordingError(f"recording larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    try:
        frames = list(iter_frames(data))
    except (NgfError, OSError, EOFError, gzip.BadGzipFile) as exc:
        raise RecordingError(f"not a valid NGF recording: {exc}") from exc
    if not frames:
        raise RecordingError("recording contains no frames")
    return frames


def _gzipped(data: bytes) -> bytes:
    return data if data[:2] == b"\x1f\x8b" else gzip.compress(data, mtime=0)


async def store_recording(
    session: AsyncSession, game_id: int, data: bytes, *, prune_frames: bool = True
) -> StoredRecording:
    """Validate and store ``data`` as the recording of ``game_id`` (idempotent)."""
    frames = decode(data)
    blob = _gzipped(data)
    sha = hashlib.sha256(blob).hexdigest()
    existing = await session.get(GameRecording, game_id)
    created = existing is None or existing.sha256 != sha
    if created:
        await session.execute(
            insert(GameRecording)
            .values(
                game_id=game_id,
                ngf_gz=blob,
                sha256=sha,
                size_bytes=len(blob),
                frame_count=len(frames),
            )
            .on_conflict_do_update(
                index_elements=[GameRecording.game_id],
                set_={
                    "ngf_gz": blob,
                    "sha256": sha,
                    "size_bytes": len(blob),
                    "frame_count": len(frames),
                    "received_at": datetime.now(UTC),
                },
            )
        )
    pruned = 0
    if prune_frames:
        result = await session.execute(delete(GameFrame).where(GameFrame.game_id == game_id))
        pruned = result.rowcount or 0  # type: ignore[attr-defined]
    return StoredRecording(game_id, len(blob), sha, len(frames), created, pruned)


async def recording_bytes(session: AsyncSession, game_id: int) -> tuple[bytes, str] | None:
    """The game's NGF (gzip) and its origin ("recording" or "live"), or None."""
    stored = await session.get(GameRecording, game_id)
    if stored is not None:
        return stored.ngf_gz, "recording"
    rows = (
        await session.scalars(
            select(GameFrame).where(GameFrame.game_id == game_id).order_by(GameFrame.seq)
        )
    ).all()
    if not rows:
        return None
    blank = [0] * playfield.CELLS
    frames: list[NgfFrame] = []
    last_field = blank
    for row in rows:
        if row.playfield is not None:
            last_field = playfield.unpack(row.playfield)
        frames.append(
            NgfFrame(
                gameid=game_id & 0xFFFF,
                ctime_ms=row.t_ms,
                score=row.score,
                lines=row.lines,
                level=row.level,
                preview=row.next_piece,
                field=last_field,
            )
        )
    return encode_file(frames), "live"


@dataclass(frozen=True, slots=True)
class ImportedGame:
    game_id: int
    score: int | None
    frames: int


async def import_ngf(
    session: AsyncSession,
    data: bytes,
    *,
    player_id: int | None,
    station_id: str | None,
    started_at: datetime | None = None,
) -> list[ImportedGame]:
    """Create one finished game per game contained in an NGF file."""
    games = [g for g in split_games(decode(data)) if len(g) >= MIN_IMPORT_FRAMES]
    if not games:
        raise RecordingError("no game with enough frames in this file")
    base = started_at or datetime.now(UTC)
    imported: list[ImportedGame] = []
    for index, frames in enumerate(games):
        tracker = GameTracker()
        for frame in frames:
            tracker.update(frame)
        duration = max(frames[-1].ctime_ms - frames[0].ctime_ms, 0) / 1000
        start = base + timedelta(seconds=index)  # keep games of one file ordered
        game = Game(
            source="ngf_import",
            status="finished",
            player_id=player_id,
            station_id=station_id,
            started_at=start,
            ended_at=start + timedelta(seconds=duration),
            duration_s=duration,
            start_level=tracker.start_level,
            end_level=tracker.level,
            score=tracker.score,
            lines=tracker.lines,
            clears_single=tracker.clears["single"],
            clears_double=tracker.clears["double"],
            clears_triple=tracker.clears["triple"],
            clears_tetris=tracker.clears["tetris"],
            tetris_rate=tracker.tetris_rate,
            burn=tracker.burn,
            max_drought=tracker.max_drought,
            pieces=tracker.pieces or None,
        )
        session.add(game)
        await session.flush()
        await store_recording(session, game.id, encode_file(frames), prune_frames=False)
        imported.append(ImportedGame(game.id, tracker.score, len(frames)))
    return imported
