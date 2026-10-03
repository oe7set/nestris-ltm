"""In-memory live state of every station, with change notifications.

The hub is the single place overlays, the admin dashboard and (later) the
scene logic read live data from. It never touches the database.
Subscribers get a bounded queue; a subscriber that cannot keep up loses
messages rather than slowing down the ingest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from nestris_ltm.ingest.payloads import LivePayload, PlayerPayload, StatusPayload
from nestris_ltm.live.broadcast import Broadcaster

log = structlog.get_logger(__name__)

# A station is "stale" when no status arrived for this long (it publishes
# every 10 s by default).
STALE_AFTER = timedelta(seconds=35)
# Live data this recent proves the station is up, whatever the last status said
# (e.g. a stale "offline" last will after a client-id takeover).
LIVE_PROVES_ONLINE = timedelta(seconds=5)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class StationState:
    id: str
    status: StatusPayload | None = None
    status_at: datetime | None = None
    player: PlayerPayload | None = None
    player_at: datetime | None = None
    live: LivePayload | None = None
    live_at: datetime | None = None
    # Display name of the player resolved from the card (set by the ingest).
    player_nickname: str | None = None
    messages: int = 0
    last_message_at: datetime | None = None

    def online(self, now: datetime) -> bool:
        if self.live_at is not None and now - self.live_at <= LIVE_PROVES_ONLINE:
            return True
        return self.status is not None and self.status.state == "online"

    def stale(self, now: datetime) -> bool:
        last = max((t for t in (self.status_at, self.live_at) if t is not None), default=None)
        return last is None or now - last > STALE_AFTER

    def snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        return {
            "id": self.id,
            "name": self.status.name if self.status else None,
            "online": self.online(now),
            "stale": self.stale(now),
            "status": self.status.model_dump(mode="json") if self.status else None,
            "status_at": _iso(self.status_at),
            "card": (
                self.player.player.model_dump(mode="json")
                if self.player and self.player.player
                else None
            ),
            "card_present": bool(self.player and self.player.present),
            "player_nickname": self.player_nickname,
            "live": self.live.model_dump(mode="json") if self.live else None,
            "live_at": _iso(self.live_at),
            "messages": self.messages,
            "last_message_at": _iso(self.last_message_at),
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class LiveHub(Broadcaster):
    def __init__(self) -> None:
        super().__init__()
        self._stations: dict[str, StationState] = {}
        # Synchronous in-process listeners (e.g. the scene engine); they see
        # every message right away, before any WebSocket client.
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(listener)

    def publish(self, message: dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(message)
            except Exception:
                log.exception("live listener failed", type=message.get("type"))
        super().publish(message)

    # ------------------------------------------------------------ state

    def station(self, station_id: str) -> StationState:
        state = self._stations.get(station_id)
        if state is None:
            state = self._stations[station_id] = StationState(id=station_id)
        return state

    def forget(self, station_id: str) -> None:
        if self._stations.pop(station_id, None) is not None:
            self.publish({"type": "station_removed", "station": station_id})

    def stations(self) -> list[StationState]:
        return sorted(self._stations.values(), key=lambda s: s.id)

    def _touch(self, state: StationState) -> datetime:
        now = _now()
        state.messages += 1
        state.last_message_at = now
        return now

    def update_status(self, station_id: str, payload: StatusPayload) -> None:
        state = self.station(station_id)
        state.status = payload
        state.status_at = self._touch(state)
        self._publish_station(state)

    def update_player(self, station_id: str, payload: PlayerPayload) -> None:
        state = self.station(station_id)
        state.player = payload
        state.player_at = self._touch(state)
        if not payload.present:
            state.player_nickname = None
        self._publish_station(state)

    def set_player_nickname(self, station_id: str, nickname: str | None) -> None:
        state = self.station(station_id)
        if state.player_nickname != nickname:
            state.player_nickname = nickname
            self._publish_station(state)

    def update_live(self, station_id: str, payload: LivePayload) -> None:
        state = self.station(station_id)
        state.live = payload
        state.live_at = self._touch(state)
        self.publish(
            {
                "type": "live",
                "station": station_id,
                "data": payload.model_dump(mode="json"),
            }
        )

    def game_event(self, station_id: str, kind: str, data: dict[str, Any]) -> None:
        """Announce a stored game event (start/cheat/end) to subscribers."""
        self.publish({"type": "game_event", "station": station_id, "kind": kind, "data": data})

    def snapshot(self) -> list[dict[str, Any]]:
        now = _now()
        return [s.snapshot(now) for s in self.stations()]

    def _publish_station(self, state: StationState) -> None:
        self.publish({"type": "station", "station": state.id, "data": state.snapshot()})
