"""Remote configuration of the stations (nestris-core docs/STATION.md).

NestrisLTM keeps a template for all stations (``settings`` key
``stations.config_template``) and per-station overrides (``station_configs``).
A station is *managed* when a template exists or it has an override row;
only managed stations get a config. The desired set is sent whenever it
differs from what the station reports on its retained ``config`` topic: after
an edit, and when the station (re)connects. The station stores it, restarts
after the running game, and reports the result.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import station_config as sc
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Station, StationConfig
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import app_settings

log = structlog.get_logger(__name__)

TEMPLATE_KEY = "stations.config_template"
# The same set is not resent within this time (the station answers within
# a second; a reconnect storm must not flood it).
RESEND_AFTER_S = 30.0

CommandSink = Callable[[str, dict[str, Any]], Awaitable[bool]]


class StationConfigError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def get_template(session: AsyncSession) -> dict[str, Any] | None:
    row = await app_settings.get(session, TEMPLATE_KEY)
    return dict(row.get("values") or {}) if row is not None else None


async def desired_for(
    session: AsyncSession, station_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(desired, overrides)``; desired is ``None`` for an unmanaged station."""
    template = await get_template(session)
    row = await session.get(StationConfig, station_id)
    overrides = dict(row.overrides) if row is not None else None
    if template is None and overrides is None:
        return None, None
    return sc.merge(template or {}, overrides or {}), overrides


class StationConfigService:
    def __init__(self, db: DatabaseManager, hub: LiveHub, command_sink: CommandSink) -> None:
        self.db = db
        self.hub = hub
        self.command_sink = command_sink
        # station -> (revision, monotonic time) of the last set sent.
        self._sent: dict[str, tuple[int, float]] = {}

    def _online(self, station_id: str) -> bool:
        st = next((s for s in self.hub.stations() if s.id == station_id), None)
        return st is not None and st.online(datetime.now(UTC))

    async def sync(self, station_id: str, *, force: bool = False) -> dict[str, Any] | None:
        """Send the desired set if the station does not hold it yet.

        Returns the command sent, or ``None`` when nothing had to go out.
        Raises :class:`StationConfigError` only with ``force``.
        """
        if not self.db.is_ready:
            if force:
                raise StationConfigError("db_unavailable", "database not ready")
            return None
        async with self.db.session() as session:
            desired, _ = await desired_for(session, station_id)
        state = self.hub.station(station_id)
        report = state.config
        if desired is None:
            if force:
                raise StationConfigError("unmanaged", "no config set for this station")
            return None
        if report is None:
            # Station older than 0.3.0 (no config topic) or not heard yet.
            if force:
                raise StationConfigError(
                    "unsupported", "the station does not report a config (update it to 0.3.0+)"
                )
            return None
        if not self._online(station_id):
            if force:
                raise StationConfigError("offline", f"station {station_id} is not online")
            return None
        rev = sc.revision(desired)
        if not force and not sc.needs_send(rev, report.rev, report.state):
            return None
        last = self._sent.get(station_id)
        if not force and last and last[0] == rev and time.monotonic() - last[1] < RESEND_AFTER_S:
            return None
        command = {"type": "station_config", "op": "set", "rev": rev, "values": desired}
        if not await self.command_sink(station_id, command):
            if force:
                raise StationConfigError("mqtt_offline", "no MQTT connection")
            return None
        self._sent[station_id] = (rev, time.monotonic())
        log.info("station config sent", station=station_id, rev=rev)
        return command

    async def on_report(self, station_id: str) -> None:
        """A station reported its config: catch it up if needed."""
        try:
            await self.sync(station_id)
        except Exception:
            log.exception("station config sync failed", station=station_id)

    async def sync_all(self) -> list[str]:
        """After a template change: every station that reports a config."""
        sent = []
        for st in self.hub.stations():
            if st.config is not None and await self.sync(st.id) is not None:
                sent.append(st.id)
        return sent

    async def request(self, station_id: str, op: str) -> None:
        """``get`` or ``list_devices`` (the station answers on ``config``)."""
        if not self._online(station_id):
            raise StationConfigError("offline", f"station {station_id} is not online")
        if not await self.command_sink(station_id, {"type": "station_config", "op": op}):
            raise StationConfigError("mqtt_offline", "no MQTT connection")

    async def overview(self, session: AsyncSession) -> dict[str, Any]:
        template = await get_template(session)
        rows = {r.station_id: r for r in (await session.scalars(select(StationConfig))).all()}
        stations = (await session.scalars(select(Station).order_by(Station.id))).all()
        now = datetime.now(UTC)
        live = {s.id: s for s in self.hub.stations()}
        ids = sorted({s.id for s in stations} | set(live))
        names = {s.id: s.name for s in stations}
        out = []
        for sid in ids:
            row = rows.get(sid)
            overrides = dict(row.overrides) if row is not None else None
            managed = template is not None or overrides is not None
            desired = sc.merge(template or {}, overrides or {}) if managed else None
            st = live.get(sid)
            report = st.config if st else None
            out.append(
                {
                    "id": sid,
                    "name": names.get(sid) or (st.status.name if st and st.status else None),
                    "known": sid in names,
                    "online": bool(st and st.online(now)),
                    "managed": managed,
                    "overrides": overrides,
                    "updated_by": row.updated_by if row else None,
                    "updated_at": row.updated_at.isoformat() if row else None,
                    "desired": desired,
                    "desired_rev": sc.revision(desired) if desired is not None else None,
                    "report": report.model_dump(mode="json") if report else None,
                    "in_sync": (
                        report is not None
                        and desired is not None
                        and report.rev == sc.revision(desired)
                        and report.state == "applied"
                    ),
                }
            )
        return {"template": template, "allowed": list(sc.ALLOWED), "stations": out}
