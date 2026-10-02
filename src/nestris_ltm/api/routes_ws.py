"""WebSocket feed of live station state.

``/ws/live`` sends ``{"type": "snapshot", "stations": [...]}`` on connect,
then every hub message (``station``, ``live``, ``game_event``). Clients may
send ``{"type": "ping"}`` and get ``{"type": "pong"}``.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nestris_ltm.live.hub import LiveHub, Subscription

router = APIRouter()


@router.websocket("/ws/live")
async def live_feed(websocket: WebSocket) -> None:
    hub: LiveHub = websocket.app.state.runtime.hub
    await websocket.accept()
    sub = hub.subscribe()
    try:
        await websocket.send_json({"type": "snapshot", "stations": hub.snapshot()})
        receiver = asyncio.create_task(_receive(websocket, sub))
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
        hub.unsubscribe(sub)


async def _receive(websocket: WebSocket, sub: Subscription) -> None:
    """Answer pings until the client disconnects.

    Replies go through the subscription queue so only one task ever sends.
    """
    while True:
        message = await websocket.receive_json()
        if isinstance(message, dict) and message.get("type") == "ping":
            sub.queue.put_nowait({"type": "pong"})
