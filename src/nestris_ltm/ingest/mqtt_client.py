"""MQTT subscriber: keeps a connection to the broker and feeds the ingest.

The session is persistent (fixed client id, ``clean_session=False``) so the
broker queues QoS 1 events while NestrisLTM is not running. Note that the
broker only keeps those across its own restarts with ``persistence true``
in ``mosquitto.conf``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import aiomqtt
import structlog

from nestris_ltm.config import MqttSettings
from nestris_ltm.ingest.service import IngestService

log = structlog.get_logger(__name__)


class MqttIngest:
    def __init__(self, settings: MqttSettings, ingest: IngestService) -> None:
        self.settings = settings
        self.ingest = ingest
        self.prefix = settings.topic_prefix.rstrip("/")
        self.connected = False
        self.connected_since: datetime | None = None
        self.last_error: str | None = None
        self.connects = 0
        self.messages = 0
        self._client: aiomqtt.Client | None = None

    def subscriptions(self) -> list[tuple[str, int]]:
        p = self.prefix
        return [
            (f"{p}/+/status", 1),
            (f"{p}/+/player", 1),
            (f"{p}/+/live", 0),
            (f"{p}/+/event/#", 1),
            (f"{p}/+/update", 1),
            (f"{p}/+/config", 1),
        ]

    def _new_client(self) -> aiomqtt.Client:
        s = self.settings
        return aiomqtt.Client(
            s.host,
            s.port,
            username=s.username,
            password=s.password.get_secret_value() if s.password else None,
            identifier=s.client_id,
            clean_session=False,
            protocol=aiomqtt.ProtocolVersion.V311,
            keepalive=s.keepalive_s,
            timeout=10,
        )

    async def run(self) -> None:
        if not self.settings.enabled:
            log.info("mqtt disabled in config")
            return
        delay = 1.0
        while True:
            try:
                async with self._new_client() as client:
                    self._client = client
                    await client.subscribe(self.subscriptions())
                    self.connected = True
                    self.connected_since = datetime.now(UTC)
                    self.last_error = None
                    self.connects += 1
                    delay = 1.0
                    log.info(
                        "mqtt connected",
                        broker=f"{self.settings.host}:{self.settings.port}",
                        prefix=self.prefix,
                    )
                    async for message in client.messages:
                        self.messages += 1
                        payload = message.payload
                        if not isinstance(payload, bytes | bytearray | str):
                            continue
                        try:
                            await self.ingest.handle_message(
                                str(message.topic),
                                bytes(payload) if isinstance(payload, bytearray) else payload,
                                self.prefix,
                            )
                        except Exception:
                            log.exception("mqtt message handler failed", topic=str(message.topic))
            except aiomqtt.MqttError as exc:
                self.last_error = str(exc)
                log.warning("mqtt connection lost", error=str(exc), retry_in_s=delay)
            finally:
                self._client = None
                if self.connected:
                    self.connected = False
                    self.connected_since = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.settings.reconnect_max_s)

    async def publish_command(self, station: str, command: dict[str, Any]) -> bool:
        """Send a command to a station (``<prefix>/<station>/cmd``)."""
        client = self._client
        if client is None:
            return False
        await client.publish(f"{self.prefix}/{station}/cmd", json.dumps(command), qos=1)
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.enabled,
            "broker": f"{self.settings.host}:{self.settings.port}",
            "client_id": self.settings.client_id,
            "topic_prefix": self.prefix,
            "connected": self.connected,
            "connected_since": self.connected_since.isoformat() if self.connected_since else None,
            "connects": self.connects,
            "messages": self.messages,
            "last_error": self.last_error,
        }
