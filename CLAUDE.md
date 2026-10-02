# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

NestrisLTM (Local Tournament Manager): the host app of the Retroverse Tetris
tournament. One Python process: MQTT ingest from `nestris-station` →
PostgreSQL, FastAPI (admin REST + WebSocket + OBS overlays), PySide6 tray
shell. It replaces the old `../NestrisLTM/` and `../TournamentHigscore/`;
those stay untouched as reference. Design and roadmap:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Commands

```powershell
uv sync
uv run pytest                                  # unit tests (db tests skip without a server)
$env:NESTRIS_LTM_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<pw>@127.0.0.1:5432/postgres"
uv run pytest -m db                            # integration tests, create throwaway DBs
uv run pytest tests/test_config.py::test_unknown_key_is_rejected
uv run ruff check . ; uv run ruff format . ; uv run mypy
uv run nestris-ltm --headless                  # core only, http://localhost:7990
uv run nestris-ltm migrate                     # create DB + migrate, then exit
uv run alembic revision --autogenerate -m "..."  # new migration (reads app config)
```

## Conventions

- Code comments, docstrings and docs in **English**. The admin UI is de/en.
- **Commit messages never mention Claude** (no Co-Authored-By trailer).
- `core/` is pure domain logic (no I/O, no framework imports) and unit-tested.
- Every schema change is a new Alembic revision in `src/nestris_ltm/db/migrations/versions/`
  (`NNNN_slug.py`); `tests/test_db_bootstrap.py::test_migrations_match_models`
  fails if models and migrations drift. Never edit an applied revision.
- Enumerations are short strings with CHECK constraints, not PG enums.
- MQTT delivery is at-least-once: every ingest write is an idempotent upsert
  keyed on the station's `game_id` (`games.external_id`).
- The MQTT contract is owned by `../nestris-core/docs/STATION.md` and
  `crates/nestris-station/src/payload.rs`; keep the pydantic models in step.
- The app must start with the database down (`DatabaseManager` retries in
  the background); routes use `SessionDep`, which answers 503 until ready.
- Settings: `config.py` (TOML at `%APPDATA%\NestrisLTM\config.toml`, env
  `NESTRIS_LTM__SECTION__KEY`). Unknown keys are errors.
