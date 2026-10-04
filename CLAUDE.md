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
$env:NESTRIS_LTM_TEST_MQTT = "127.0.0.1:1883"; uv run pytest tests/test_mqtt_e2e.py
uv run pytest tests/test_config.py::test_unknown_key_is_rejected
uv run ruff check . ; uv run ruff format . ; uv run mypy
uv run nestris-ltm                             # tray app + window
uv run nestris-ltm --headless                  # core only, http://localhost:7990
uv run nestris-ltm migrate                     # create DB + migrate, then exit
uv run nestris-ltm simulate ..\*.ngf --stations station-1,station-2 --names "A,B" --speed 4
uv run alembic revision --autogenerate -m "..."  # new migration (reads app config)
cd frontend; pnpm install; pnpm build          # admin UI -> src/nestris_ltm/web/admin (git-ignored)
pnpm check; pnpm test; pnpm dev:admin          # svelte-check, vitest, Vite dev server on :5173
uv run nestris-ltm check                       # database / broker / port check (installer uses it)
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # UI + PyInstaller + installer
```

Packaging: `packaging/nestris-ltm.spec` (one folder, `NestrisLTM.exe` GUI +
`nestris-ltm.exe` console CLI; data dirs `web`, `kiosk`, `api/pages` and
`db/migrations` are shipped as files because they are read via
`importlib.resources`/Alembic, so a new resource directory must be added
there). `packaging/installer.iss` pins the PostgreSQL/Mosquitto download URLs
and SHA-256 hashes. Releases: tag `v<version>` → `.github/workflows/release.yml`.
Operations guide: `docs/OPERATIONS.md`.

## Conventions

- Code comments, docstrings and docs in **English**. The admin UI is de/en.
- **Commit messages never mention Claude** (no Co-Authored-By trailer).
- License: Apache-2.0 (`LICENSE`), attribution and third-party material in `NOTICE`.
  New third-party assets (fonts, icons, copied code) get an entry there and keep
  their own license file next to them; LICENSE and NOTICE ship with every build.
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
- On Windows the asyncio loop must be a `SelectorEventLoop` (paho/aiomqtt);
  always start the core through `runtime.run_async`.
- Station events (`event/*`) go through the durable spool (`ingest/spool.py`)
  before the database; only the spool worker writes game rows.
- `shell/` is the only place that imports Qt. The core never depends on it;
  the shell talks to the core through `Runtime` attributes (read-only) and
  `Runtime.request_shutdown()` (thread-safe).
- The single-instance pipe name includes the HTTP port, so tests and a dev
  instance on another port never touch a running production instance.
- Admin UI: Svelte 5 (runes) + TypeScript in `frontend/apps/admin`, hash routing
  (`lib/routes.ts`), all strings in `lib/i18n.svelte.ts` (de + en, same keys).
  Initial page loads use `onMount`, not `$effect`.
- Every admin route depends on `AdminDep`; every write records an audit entry
  (`services/audit.py`). New pages/views are registered in `pages.py` so the
  overview page lists them.
- `kiosk/static` is ported verbatim from TournamentHigscore (only URLs were
  rewritten to `/kiosk/static/...`, `/ws/kiosk`, `/api/tournament/...`). Keep
  it close to the original; the server side (`services/tournament.py`) speaks
  the original WebSocket protocol (`init`, `*_update`, `view_settings`, ...).
- `core/bracket.py` holds the verbatim `derive_bracket` port plus the pure
  `BracketState`; `tests/test_bracket.py` is the original test suite.
- Overlays: `frontend/apps/overlay` (served at `/o/<slug>`, bundle under
  `/overlay-assets/`). A new layout = entry in `core/layouts.py` + component in
  `frontend/apps/overlay/src/layouts/` + mapping in its `App.svelte`. All versus
  numbers come from `SceneEngine.compute_state`; overlays only display.
- `frontend/packages/nes` (`@nestris-ltm/nes`) is shared by admin and overlay:
  NES palettes/blocks, `<Playfield>`, `<NextPiece>`, the NGF decoder (keep it in
  step with `core/ngf.py`) and the replay `Timeline`.
- Every game replays as NGF via `/api/games/<id>/recording`: the station's file
  if uploaded, else synthesized from `game_frames`.
