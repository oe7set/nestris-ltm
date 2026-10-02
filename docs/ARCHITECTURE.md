# NestrisLTM architecture

## Goal

One host application for the Retroverse tournament that

- receives live state, game events and results from the capture stations
  over MQTT and stores them in PostgreSQL (schema created and migrated by the
  app itself),
- manages players, games (edit, create, hide, re-assign), events and the
  tournament bracket,
- serves OBS browser sources (single, 1v1, 2×1v1, 4 players with
  elimination modes, highscore, bracket, score train, replay),
- shows what is connected and running (diagnostics),
- starts with Windows and keeps running in the tray.

## Process layout

```
Stations ──MQTT──► Mosquitto ──► ingest (aiomqtt) ──► LiveHub (in-memory state per station)
   │                                   │                   │
   └─HTTP PUT .ngf.gz──► REST API      ▼                   ▼
                                 PostgreSQL ◄── services ──► WebSocket hub ──► OBS overlays
                                      ▲                                     ├─► highscore/bracket kiosk
                              Admin SPA (REST)                              └─► admin SPA (live status)
Qt shell: tray icon, window = QWebEngineView(admin), autostart, single instance
```

- The Qt main thread owns the tray and window. A background thread runs one
  asyncio loop with `uvicorn.Server` (FastAPI), the MQTT ingest and all
  background tasks (`runtime.Runtime`).
- `--headless` runs the same `Runtime` without Qt.
- Mosquitto runs as its own Windows service; the stations spool durable
  events until the broker acknowledges them, so results survive a host
  restart. NestrisLTM uses a persistent MQTT session for the same reason.
- The app starts even when PostgreSQL is down; `DatabaseManager` retries the
  bootstrap with backoff and the API answers 503 meanwhile.

## Decisions

| Topic | Decision |
|---|---|
| Database | New database (`nestrisltm`), Alembic migrations on startup, DB created if missing |
| Time window | `events` table; exactly one active event scopes highscore, bracket, overlays |
| Hiding | Per event: player everywhere, player from bracket only, single games, whole stations |
| Cheats / invalid | Everything counts; flagged in the UI (badge + filter) |
| RFID | Known card uid → its player (several cards per player, `player_cards`); else name on the card (case-insensitive), learning the uid; unknown names auto-create a player flagged `auto_created`; no card / blank unknown card → game "unassigned" |
| Versus | Scenes with station slots and a fixed OBS URL per scene; rounds freeze finished scores |
| Tetris diff | lead ÷ (1200 × (level + 1)) of the trailing player |
| Bracket | Single elimination 2–64 with byes and third place (ported from TournamentHigscore) |
| Recordings | Live frames from MQTT (up to 60 Hz, set `mqtt.live_max_hz = 60` on the stations) plus the station's `.ngf.gz` uploaded over HTTP |
| Auth | Overlays and kiosk views public; admin needs a login; machine clients use bearer tokens |
| Registration | RetroverseAnmledung moves from direct DB access to the REST API |
| Website uplink | Not planned |

## Schema overview

`events`, `players` (+ `player_cards`), `stations`, `games` (+ `game_frames`, `game_recordings`,
`game_cheats`), `event_player_flags`, `event_hidden_stations`,
`event_hidden_games`, `tournaments`, `scenes` (+ `scene_slots`,
`scene_rounds`, `scene_round_entries`), `admin_users`, `api_tokens`,
`settings`, `audit_log`. Source of truth: `src/nestris_ltm/db/models.py`.

A game belongs to an event when its `started_at` lies in the event window;
there is no foreign key, so changing the window re-scopes the data.

## Rounds (versus scenes)

1. A game starting on a slot's station is bound to the current round entry.
2. On `game_end` the entry freezes score, lines and level; the overlay keeps
   showing them, so the diff stays correct while others still play.
3. Another game on a finished slot is ignored until the next round.
4. When the outcome is mathematically settled (mode `top2_advance`,
   `worst_out`, `winner_only`), outcomes are set.
5. "New round" (admin, hotkey, Stream Deck via HTTP) or `auto_round` starts
   the next round.

All versus numbers are computed server-side in `SceneState` and pushed per
scene, so every layout shows identical values.

## Roadmap

1. **Skeleton**: config, logging, DB bootstrap + schema, FastAPI, CLI, tests. ✅
2. **Ingest**: MQTT client, durable event spool, idempotent upserts, frame
   buffer, LiveHub, diagnostics API + `/ws/live`, NGF codec, station
   simulator. ✅
3. **Qt shell**: tray, window, close-to-tray, single instance, autostart. ✅
4. **Admin SPA**: login, dashboard/diagnostics, players, games, events,
   stations, hiding, audit, settings (admins, API tokens), overview page. ✅
5. **Highscore and tournament**: port of TournamentHigscore logic and views.
6. **Overlays**: UI components, scenes, rounds, layouts.
7. **Recordings and replay**: NGF upload endpoint, `nestris-station`
   uploader, replay in admin and as overlay source.
8. **Registration API**: `/api/v1/players`, port RetroverseAnmledung.
9. **Packaging**: PyInstaller, Inno Setup installer, operations guide.
