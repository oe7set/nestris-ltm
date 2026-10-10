"""What needs the crew's attention right now (bell in the admin UI, dashboard).

Each item is a short, stable ``code`` with a count, a severity and where to
fix it; the UI words it (i18n ``attention.<code>``). Everything here is cheap
(a few COUNT queries and in-memory state), the UI polls it every few seconds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import EventHiddenGame, EventHiddenStation, Game, Player
from nestris_ltm.services import events

if TYPE_CHECKING:
    from nestris_ltm.runtime import Runtime

Severity = Literal["error", "warn", "info"]

# A station that sent nothing for this long and was active this recently is
# reported as gone; stations unused today stay quiet.
RECENTLY_ACTIVE = timedelta(hours=3)


@dataclass(frozen=True)
class Item:
    code: str
    severity: Severity
    count: int
    # Admin UI hash route that shows the problem.
    link: str
    # Names (station ids, ...) for the message; at most a few.
    names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stations_gone(rt: Runtime, hidden: set[str], now: datetime) -> list[str]:
    """Stations active in the last hours that are offline or silent now."""
    gone = []
    for st in rt.hub.stations():
        if st.id in hidden:
            continue
        recently = st.last_message_at is not None and now - st.last_message_at <= RECENTLY_ACTIVE
        if recently and (not st.online(now) or st.stale(now)):
            gone.append(st.id)
    return gone


def _station_items(rt: Runtime, hidden: set[str], now: datetime) -> list[Item]:
    gone = stations_gone(rt, hidden, now)
    config_errors: list[str] = []
    for st in rt.hub.stations():
        if st.id in hidden:
            continue
        if st.config is not None and st.config.state == "error":
            config_errors.append(st.id)
    items = []
    if gone:
        items.append(Item("stations_offline", "error", len(gone), "/", gone[:5]))
    if config_errors:
        items.append(
            Item("station_config_error", "warn", len(config_errors), "/stations?tab=config",
                 config_errors[:5])
        )  # fmt: skip
    return items


async def collect(rt: Runtime, session: AsyncSession) -> list[Item]:
    now = datetime.now(UTC)
    items: list[Item] = []

    if rt.settings.mqtt.enabled and not rt.mqtt.connected:
        items.append(Item("mqtt_down", "error", 1, "/"))
    failed = len(rt.spool.failed())
    if failed:
        items.append(Item("spool_failed", "error", failed, "/spool"))

    event = await events.active_event(session)
    hidden_stations: set[str] = set()
    if event is not None:
        hidden_stations = set(
            await session.scalars(
                select(EventHiddenStation.station_id).where(EventHiddenStation.event_id == event.id)
            )
        )
    items += _station_items(rt, hidden_stations, now)

    if event is not None:
        visible = and_(
            events.in_window(event),
            Game.status == "finished",
            ~exists().where(
                EventHiddenGame.event_id == event.id, EventHiddenGame.game_id == Game.id
            ),
        )
        unassigned = await session.scalar(
            select(func.count()).select_from(Game).where(visible, Game.player_id.is_(None))
        )
        if unassigned:
            items.append(
                Item("unassigned_games", "warn", int(unassigned), "/games?unassigned=true")
            )
        suspicious = await session.scalar(
            select(func.count())
            .select_from(Game)
            .where(visible, or_(Game.cheated > 0, Game.valid.is_(False)))
        )
        if suspicious:
            items.append(Item("suspicious_games", "warn", int(suspicious), "/games?flagged=true"))
    else:
        items.append(Item("no_event", "warn", 1, "/events"))

    auto = await session.scalar(
        select(func.count())
        .select_from(Player)
        .where(Player.auto_created.is_(True), Player.deleted_at.is_(None))
    )
    if auto:
        items.append(Item("auto_players", "info", int(auto), "/players?auto=true"))

    if rt.updates.update_available and rt.updates.latest is not None:
        items.append(
            Item("update_available", "info", 1, "/updates", [str(rt.updates.latest.version)])
        )
    return items
