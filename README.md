# NestrisLTM

**NestrisLTM** (Local Tournament Manager) is the host application for the
Retroverse Classic Tetris tournament. It runs on the host PC and:

- receives live data, game events and results from the capture stations
  (`nestris-station`) over **MQTT**,
- stores players, games, live frames and `.ngf.gz` recordings in
  **PostgreSQL** and creates/migrates its own schema,
- serves the **admin UI** (players, games, events, tournament, scenes,
  diagnostics) and the **OBS overlays** (single, 1v1, 2×1v1, 4 players,
  highscore, bracket),
- lives in the Windows tray and starts with Windows.

It replaces the old `NestrisLTM/` desktop app and `TournamentHigscore/`.

> Status: phase 3 (tray app with embedded window, autostart, single
> instance) on top of the MQTT ingest. The admin UI follows in phase 4. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full
> design and the roadmap.

## Requirements

- Windows 10/11 (Linux works for the headless core)
- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+ (local service on the host)
- Mosquitto MQTT broker (Windows service). Use
  [packaging/mosquitto/mosquitto.conf](packaging/mosquitto/mosquitto.conf):
  `persistence true` keeps queued results across broker restarts.

## Quick start (development)

```powershell
uv sync
uv run nestris-ltm config-path        # where the config file is expected
copy config.example.toml "$env:APPDATA\NestrisLTM\config.toml"   # then edit it
uv run nestris-ltm migrate            # create the database and schema
uv run nestris-ltm                    # tray app with window (status page for now)
uv run nestris-ltm --headless         # core only, no GUI; http://localhost:7990/
```

## The desktop app

- Starts the core (HTTP server, MQTT ingest, workers) on a background
  thread and shows it in a window (embedded browser). Other PCs, e.g. OBS
  or kiosk screens, use `http://<host-ip>:7990/`.
- **Closing the window keeps NestrisLTM running in the tray.** Quit with
  *Beenden* in the tray menu; this flushes buffered frames first.
- The tray icon shows the state: green = database and broker connected,
  orange = one of them missing, red = the core could not start (e.g. port
  in use). Its tooltip lists the details.
- *Mit Windows starten* in the tray menu registers the app in
  `HKCU\...\CurrentVersion\Run`; it then starts minimized to the tray.
- Starting it a second time only brings the running window to the front
  (`--minimized` starts hidden in the tray).

The database named in the config is created automatically if it does not
exist, and all pending migrations run on every start.

## Without hardware: the station simulator

`simulate` replays NestrisChamps recordings as one or more stations over
MQTT, with the same topics and payloads as `nestris-station`:

```powershell
uv run nestris-ltm simulate ..\0QR5AJ2RRDPNMZK5FT53K.ngf ..\YXHGT4GXCYMCTDW912MNA.ngf `
    --stations station-1,station-2 --names "Erv,Max Power" --speed 4 --loop
```

## Live data and diagnostics

| Endpoint | Content |
|---|---|
| `GET /api/health` | liveness, database state |
| `GET /api/diagnostics` | broker, database, ingest counters, spool, every station |
| `GET /api/diagnostics/logs?after_id=0&level=INFO` | recent log records |
| `WS /ws/live` | snapshot of all stations, then `station`, `live`, `game_event` messages |

## How results are stored

- `event/game_start|cheat|game_end` are written to a durable spool
  (`<data_dir>/spool`) before they are processed, then applied in order.
  Invalid events go to `spool/failed/` with a `.reason.txt`.
- All writes are idempotent upserts keyed on the station's `game_id`, so
  re-delivered or out-of-order events are harmless. Games edited in the admin
  UI are never overwritten by a re-delivery.
- Live frames (up to 60 Hz) are batched into `game_frames` once per second.
- Players are resolved from the RFID card: a known card uid maps to its
  player (a player may own several cards), otherwise the name on the card is
  matched case-insensitively; unknown names create a player flagged
  `auto_created`. Blank unknown cards and games without a card stay
  unassigned.
- MQTT uses a persistent session (fixed client id), so the broker queues
  results while NestrisLTM is not running.

## Configuration

Settings are read (later wins) from built-in defaults, the TOML file
(`%APPDATA%\NestrisLTM\config.toml`, override with `NESTRIS_LTM_CONFIG` or
`--config`) and environment variables `NESTRIS_LTM__<SECTION>__<KEY>`, for
example `NESTRIS_LTM__DATABASE__PASSWORD`. See
[config.example.toml](config.example.toml) for every key.

## Development

```powershell
uv run pytest                          # unit tests
$env:NESTRIS_LTM_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<pw>@127.0.0.1:5432/postgres"
uv run pytest -m db                    # database integration tests (create throwaway DBs)
$env:NESTRIS_LTM_TEST_MQTT = "127.0.0.1:1883"
uv run pytest tests/test_mqtt_e2e.py   # simulator -> broker -> ingest -> database
uv run ruff check . ; uv run ruff format --check . ; uv run mypy
uv run alembic revision --autogenerate -m "describe change"   # new migration
```
