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

> Status: feature-complete for the first event (phases 1–9). Design and
> roadmap: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). **Installing and
> running it at an event: [docs/OPERATIONS.md](docs/OPERATIONS.md).**

## Download

**[Latest release](https://github.com/oe7set/nestris-ltm/releases/latest)**: run
`NestrisLTM-Setup-<version>.exe` on the host PC (tournament server) (or unpack the portable zip).
Every release is signed (`SHA256SUMS.txt` + `.sig`, see
`nestris-ltm/docs/UPDATES.md`). Beta versions are listed under
[all releases](https://github.com/oe7set/nestris-ltm/releases).

## Install and update (Windows)

Download `NestrisLTM-Setup-<version>.exe` from the GitHub releases and run
it. It installs or reuses PostgreSQL and Mosquitto, sets up the firewall and
autostart, writes the database connection and checks everything at the end.
Details: [docs/OPERATIONS.md](docs/OPERATIONS.md). Later versions are
offered by the app itself (admin page *Updates*, tray balloon): signed
GitHub releases, database backup before installing, one click.

## Requirements

- Windows 10/11 (Linux works for the headless core)
- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+ (local service on the host)
- Node.js 22+ and pnpm (only to build the admin UI from source)
- Mosquitto MQTT broker (Windows service). Use
  [packaging/mosquitto/mosquitto.conf](packaging/mosquitto/mosquitto.conf):
  `persistence true` keeps queued results across broker restarts.

## Quick start (development)

```powershell
uv sync
uv run nestris-ltm config-path        # where the config file is expected
copy config.example.toml "$env:APPDATA\NestrisLTM\config.toml"   # then edit it
uv run nestris-ltm migrate            # create the database and schema
cd frontend; pnpm install; pnpm build; cd ..   # admin UI -> src/nestris_ltm/web/admin
uv run nestris-ltm                    # tray app with window (status page for now)
uv run nestris-ltm --headless         # core only, no GUI; http://localhost:7990/
```

## First start and sign-in

On the first start the window asks for the first admin account (only
possible on the host PC itself). **The desktop app signs in by itself** (it
sends a per-start token with every request), so on the host PC no password
is needed. Other devices sign in at `http://<host-ip>:7990/`; with
*Angemeldet bleiben* (default) that browser stays signed in for 30 days and
the period renews while it is used, without it the session ends when the
browser closes (at most 12 h). Further accounts and API tokens are managed
under *Einstellungen*. Forgotten password:
`uv run nestris-ltm set-admin-password <name>` on the host.

Without a frontend build `/` shows a plain status page; `/status` always
does.

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

**Card readers at the stations:** when a player places a card, NestrisLTM
sends the station's reader a `show` command (reader protocol v2,
`../nestris-rfid-reader/docs/PROTOCOL.md`) with the nickname and the
player's place and best score in the active event, e.g. *Erv / Platz 3 ·
159.867* (`services/reader_display.py`). The dashboard shows each station's
reader state (`outdated` = old reader firmware) and firmware version.

## Highscore and tournament

- `http://<host>:7990/view/highscore` is the full-screen display ported from
  TournamentHigscore with all of its animations: FLIP flights between list
  and bracket, score-train count-up, live banners (new record, lead change,
  milestone), CRT/tetromino ambiente, victory bursts and the champion
  celebration (podium, confetti, rockets). Options: `?only=highscore`,
  `?only=bracket`, `?transparent=1` (OBS), `?layout=portrait` (screen turned
  upright, 9:16: highscore on top, the bracket below zoomed to fit).
- It shows the **active event**: the best game per player inside the event
  window, running games live (green dot), without hidden players, stations
  and games.
- *Turnier* in the admin UI embeds the original console: tournament size,
  FIX/RESET/UNSEED, click a player to set the winner, *disable* = the event
  flag "nur im Turnierbaum ausblenden", plus the display remote control
  (font size, autoscroll, scroll position, effects, banners, transparency,
  celebration). Bracket state, view settings and the celebration switch are
  stored in the database and survive restarts.

## OBS overlays (scenes)

- *Szenen* in the admin UI: a scene has a fixed URL `http://<host>:7990/o/<slug>`,
  a layout, a mode and one station per slot. Add it in OBS as a browser
  source, 1920×1080, transparent; cameras go below/beside it in OBS.
  Changing layout or stations happens in the admin UI only.
- Layouts: `single`, `single_compact`, `1v1`, `2x1v1` (slots 1 vs 2 and
  3 vs 4), `4p` (modes: top 2 advance, last place out, winner only).
- Playfields render at up to 60 Hz in the NES level colours; scores count
  up, a tetris flashes the board, outcomes are stamped (WEITER / RAUS /
  SIEGER), drought ≥ 13 blinks.
- Versus numbers are computed on the server: difference, lead in tetrises
  at the trailing player's level, pace to level 29, difference graph,
  "needs N tetrises to win/advance" once the leader has topped out.
- Rounds: the first game on a slot's station is bound to the slot; when it
  ends the result is frozen and stays on screen while the others play; later
  games on that slot are ignored until *Neue Runde* (or automatically with
  *Auto-Runde*). *Slot zurücksetzen* lets one slot play again.
- Stream Deck: `POST /api/scenes/<slug>/rounds` with an API token that has
  the `scenes` scope starts the next round.

## Recordings and replay

- Stations with `[host] url/token_file` (nestris-core `docs/STATION.md`)
  upload every game's complete `.ngf.gz` after it ended. NestrisLTM stores
  it and deletes that game's 60 Hz live frames (a 7-minute game is ~50 KB
  instead of several MB). Create the token under *Einstellungen → API-Tokens*
  with the `stations` scope.
- Every game page has a replay player (play/pause, 0.25×–8×, scrubbing,
  frame steps; space and arrow keys). Without the station's file it replays
  the stored live frames.
- *Im Overlay abspielen* sends a game to a scene with the `replay` layout,
  e.g. to show a highlight on stream.
- *Spiele → NGF importieren* imports `.ngf`/`.ngf.gz` files as finished
  games; *NGF herunterladen* exports any game.

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

Releases: bump `version` in `pyproject.toml`, push a tag `v<version>`;
`.github/workflows/release.yml` builds the installer on Windows and publishes
it. CI (`ci.yml`) runs lint, mypy, all tests (incl. database tests) and the
frontend checks on every push. Local build: `packaging\build.ps1`.

```powershell
uv run pytest                          # unit tests
$env:NESTRIS_LTM_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<pw>@127.0.0.1:5432/postgres"
uv run pytest -m db                    # database integration tests (create throwaway DBs)
$env:NESTRIS_LTM_TEST_MQTT = "127.0.0.1:1883"
uv run pytest tests/test_mqtt_e2e.py   # simulator -> broker -> ingest -> database
uv run ruff check . ; uv run ruff format --check . ; uv run mypy
cd frontend; pnpm check; pnpm test       # svelte-check + vitest
pnpm dev:admin                           # admin UI with hot reload on :5173 (proxies to :7990)
uv run alembic revision --autogenerate -m "describe change"   # new migration
```

## License

Apache License 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Copyright 2026 Erwin Spitaler (OE7SET) – Retroverse.
