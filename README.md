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

> Status: phase 1 (core skeleton, configuration, database bootstrap and
> schema). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full
> design and the roadmap.

## Requirements

- Windows 10/11 (Linux works for the headless core)
- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+ (local service on the host)
- Mosquitto MQTT broker (Windows service), from phase 2 on

## Quick start (development)

```powershell
uv sync
uv run nestris-ltm config-path        # where the config file is expected
copy config.example.toml "$env:APPDATA\NestrisLTM\config.toml"   # then edit it
uv run nestris-ltm migrate            # create the database and schema
uv run nestris-ltm --headless         # run the core; http://localhost:7990/api/health
```

The database named in the config is created automatically if it does not
exist, and all pending migrations run on every start.

## Configuration

Settings are read (later wins) from built-in defaults, the TOML file
(`%APPDATA%\NestrisLTM\config.toml`, override with `NESTRIS_LTM_CONFIG` or
`--config`) and environment variables `NESTRIS_LTM__<SECTION>__<KEY>`, for
example `NESTRIS_LTM__DATABASE__PASSWORD`. See
[config.example.toml](config.example.toml) for every key.

## Development

```powershell
uv run pytest                          # unit tests
$env:NESTRIS_LTM_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:secret@127.0.0.1:5432/postgres"
uv run pytest -m db                    # database integration tests (create throwaway DBs)
uv run ruff check . ; uv run ruff format --check . ; uv run mypy
uv run alembic revision --autogenerate -m "describe change"   # new migration
```
