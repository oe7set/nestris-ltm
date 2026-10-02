"""Fan-out of JSON messages to WebSocket subscribers.

Each subscriber gets a bounded queue; a subscriber that cannot keep up loses
messages (counted in ``dropped``) instead of slowing down the producer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

# 8 stations x 60 Hz = 480 messages/s; this absorbs about 4 s of client lag.
SUBSCRIBER_QUEUE_SIZE = 2048


@dataclass(eq=False)
class Subscription:
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(SUBSCRIBER_QUEUE_SIZE)
    )
    dropped: int = 0


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: set[Subscription] = set()

    def subscribe(self) -> Subscription:
        sub = Subscription()
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, message: dict[str, Any]) -> None:
        for sub in self._subscribers:
            try:
                sub.queue.put_nowait(message)
            except asyncio.QueueFull:
                sub.dropped += 1
