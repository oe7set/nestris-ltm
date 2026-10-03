"""WebSocket feeds.

- ``/ws/live``  : station live state. A ``{"type": "snapshot", "stations": [...]}``
  on connect, then every hub message (``station``, ``live``, ``game_event``).
- ``/ws/kiosk`` : highscore + tournament in the TournamentHigscore protocol
  (``{"type": ..., "data": ...}``, starting with ``init``).
- ``/ws/scene/<slug>``: one overlay scene (see ``services/scenes.py``).

Clients may send ``{"type": "ping"}``; the answer is ``pong``.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nestris_ltm.live.broadcast import Broadcaster, Subscription

router = APIRouter()


@router.websocket("/ws/live")
async def live_feed(websocket: WebSocket) -> None:
    hub = websocket.app.state.runtime.hub
    await serve(websocket, hub, lambda: _live_init(hub), pong={"type": "pong"})


@router.websocket("/ws/kiosk")
async def kiosk_feed(websocket: WebSocket) -> None:
    tournament = websocket.app.state.runtime.tournament

    async def init() -> dict[str, Any]:
        return {"type": "init", "data": await tournament.snapshot()}

    await serve(websocket, tournament, init, pong={"type": "pong", "data": {}})


@router.websocket("/ws/scene/{slug}")
async def scene_feed(websocket: WebSocket, slug: str) -> None:
    engine = websocket.app.state.runtime.scenes
    runtime = engine.scenes.get(slug)
    if runtime is None:
        await websocket.close(code=4404, reason="unknown scene")
        return

    async def init() -> dict[str, Any]:
        return {"type": "init", "data": engine.snapshot(slug)}

    await serve(websocket, runtime.channel, init, pong={"type": "pong"})


async def _live_init(hub: Any) -> dict[str, Any]:
    return {"type": "snapshot", "stations": hub.snapshot()}


async def serve(
    websocket: WebSocket,
    source: Broadcaster,
    initial: Any,
    *,
    pong: dict[str, Any],
) -> None:
    """Send ``initial()`` then every message of ``source`` until the client leaves."""
    await websocket.accept()
    # Subscribe before building the snapshot so no update in between is lost.
    sub = source.subscribe()
    try:
        await websocket.send_json(await initial())
        receiver = asyncio.create_task(_receive(websocket, sub, pong))
        try:
            while not receiver.done():
                getter = asyncio.create_task(sub.queue.get())
                done, _ = await asyncio.wait(
                    {getter, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    await websocket.send_json(getter.result())
                else:
                    getter.cancel()
        finally:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await receiver
    except WebSocketDisconnect:
        pass
    finally:
        source.unsubscribe(sub)


async def _receive(websocket: WebSocket, sub: Subscription, pong: dict[str, Any]) -> None:
    """Answer pings until the client disconnects (replies go through the queue,
    so only one task ever sends)."""
    while True:
        message = await websocket.receive_json()
        if isinstance(message, dict) and message.get("type") == "ping":
            sub.queue.put_nowait(pong)
