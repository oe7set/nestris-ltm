"""Recordings: station upload, download/replay, NGF import.

Station upload (documented in nestris-core/docs/STATION.md)::

    PUT /api/stations/<station>/games/<game_id>/ngf
    Authorization: Bearer nltm_...        (API token with the "stations" scope)
    Content-Type: application/gzip        (the .ngf.gz; raw .ngf is accepted too)
    X-NGF-SHA256: <hex>                   (optional, checked when present)

    201 stored · 200 identical file already stored · 404 game not known yet
    (retry later: the game_end may still be on its way) · 409 the game
    belongs to another station · 400 not an NGF · 413 too large
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from nestris_ltm.api.auth import AdminDep, Principal, require_scope
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.db.models import Game, Player, Station
from nestris_ltm.services import audit, recordings

router = APIRouter(tags=["recordings"])
StationDep = Annotated[Principal, Depends(require_scope("stations"))]


async def _body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and int(declared) > recordings.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "recording too large")
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > recordings.MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "recording too large")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty body")
    return data


@router.put("/api/stations/{station_id}/games/{external_id}/ngf")
async def upload_from_station(
    station_id: str,
    external_id: str,
    request: Request,
    response: Response,
    principal: StationDep,
    session: SessionDep,
) -> dict[str, Any]:
    data = await _body(request)
    claimed = request.headers.get("x-ngf-sha256")
    if claimed and hashlib.sha256(data).hexdigest() != claimed.strip().lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-NGF-SHA256 does not match the body")
    async with session.begin():
        game = await session.scalar(select(Game).where(Game.external_id == external_id))
        if game is None:
            # The game_end may still be queued at the broker; the station retries.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "game not known yet")
        if game.station_id not in (None, station_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "game belongs to another station")
        try:
            stored = await recordings.store_recording(session, game.id, data)
        except recordings.RecordingError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        if stored.created:
            await audit.record(
                session, actor=principal.actor, action="recording", entity="game",
                entity_id=game.id,
                after={"size_bytes": stored.size_bytes, "frames": stored.frame_count,
                       "live_frames_pruned": stored.frames_pruned},
            )  # fmt: skip
    # Live frames still in flight for this game are no longer needed.
    get_runtime(request).frames.discard(external_id)
    response.status_code = status.HTTP_201_CREATED if stored.created else status.HTTP_200_OK
    return {
        "game_id": game.id,
        "size_bytes": stored.size_bytes,
        "sha256": stored.sha256,
        "frames": stored.frame_count,
        "live_frames_pruned": stored.frames_pruned,
    }


@router.get("/api/games/{game_id}/recording")
async def download(game_id: int, session: SessionDep, download: bool = False) -> Response:
    """The game as NGF (gzip). Public: overlays replay games with it.

    ``X-Recording-Source`` says whether it is the station's complete recording
    or built from the stored live frames.
    """
    result = await recordings.recording_bytes(session, game_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no recording or live frames for this game")
    data, source = result
    headers = {"X-Recording-Source": source, "Cache-Control": "no-store"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="game-{game_id}.ngf.gz"'
    return Response(data, media_type="application/gzip", headers=headers)


@router.post("/api/games/import", status_code=status.HTTP_201_CREATED)
async def import_ngf(
    request: Request,
    principal: AdminDep,
    session: SessionDep,
    player_id: int | None = None,
    station_id: Annotated[str | None, Query(max_length=64)] = None,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Import an .ngf/.ngf.gz file (request body) as finished games."""
    data = await _body(request)
    async with session.begin():
        if player_id is not None and await session.get(Player, player_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "player does not exist")
        if station_id and await session.get(Station, station_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "station does not exist")
        try:
            games = await recordings.import_ngf(
                session, data, player_id=player_id, station_id=station_id or None,
                started_at=started_at,
            )  # fmt: skip
        except recordings.RecordingError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        for g in games:
            await audit.record(
                session, actor=principal.actor, action="import", entity="game", entity_id=g.game_id,
                after={"score": g.score, "frames": g.frames, "player_id": player_id},
            )  # fmt: skip
    return {"games": [{"id": g.game_id, "score": g.score, "frames": g.frames} for g in games]}
