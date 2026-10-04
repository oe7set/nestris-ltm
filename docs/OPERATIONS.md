# Operations guide: NestrisLTM

How to install, run, back up and troubleshoot NestrisLTM on the host PC of
the tournament. Design: [ARCHITECTURE.md](ARCHITECTURE.md).

## Overview

```
stations (nestris-station) ──MQTT 1883──► Mosquitto ──► NestrisLTM ──► PostgreSQL
            └──HTTP 7990 (recording upload)──────────────────┘
OBS / kiosk screens / player terminal ──HTTP 7990──► NestrisLTM
```

Everything runs on the host PC: **PostgreSQL** and **Mosquitto** as Windows
services, **NestrisLTM** as a tray app of the signed-in user.

## Install

Run `NestrisLTM-Setup-<version>.exe` (needs admin rights) as the user that
will run the tournament.

| Wizard page | What happens |
|---|---|
| Components | *PostgreSQL 18* and *Mosquitto*: installed if missing (downloaded from the official sources, SHA-256 checked), otherwise the existing installation is used. Untick them to use servers elsewhere. |
| Tasks | Autostart in the tray at sign-in; firewall rules for TCP 7990 (NestrisLTM) and 1883 (MQTT), limited to the local subnet. |
| Database | New PostgreSQL: choose the password of the user `postgres` (**write it down**). Existing PostgreSQL: its port is detected; enter the password of its user (empty keeps the current NestrisLTM setting). |
| Check | After the installation the result of `nestris-ltm check` (database, broker, port) is shown. |

The installer also

- sets the PostgreSQL and Mosquitto services to **start automatically**,
- writes [packaging/mosquitto/mosquitto.conf](../packaging/mosquitto/mosquitto.conf)
  to `C:\Program Files\mosquitto\mosquitto.conf` (an existing different file
  is kept as `mosquitto.conf.before-nestrisltm`) and restarts the broker:
  `persistence true` keeps queued results across broker restarts, and
  anonymous access is allowed (fine on a closed tournament LAN, see
  [Security](#security)),
- writes the database connection to `%APPDATA%\NestrisLTM\config.toml`.

The NestrisLTM database (`nestrisltm`) and its tables are created by the app
on its first start. An update is the same setup run again; data and settings
stay.

### First start

1. NestrisLTM opens its window: create the **first admin account** (only
   possible on the host PC itself).
2. *Einstellungen → API-Tokens*: create tokens for the stations (scope
   `stations`) and the player terminal (scope `terminal`).
3. *Events*: create the event and activate it.
4. Stations: in each `station.toml` set the `[mqtt] host` to the host PC's IP
   and the `[host]` URL `http://<host-ip>:7990` plus the token file; set
   `live_max_hz = 60`. The dashboard shows them as soon as they connect.

## Running

- **Closing the window keeps NestrisLTM running in the tray.** *Beenden* in
  the tray menu stops it (buffered live frames are written first).
- Tray icon: green = database and broker OK, orange = one missing, red =
  core not running. The tooltip has details; *Diagnose* in the admin UI shows
  stations, MQTT rate, errors and the live log.
- The admin UI and all displays are at `http://<host-ip>:7990/` (overview of
  all pages: `/#/pages`). OBS browser sources use `/o/<scene>`.
- Station results are written to a durable spool first. If the database is
  down, nothing is lost: results are stored when it is back. Results sent
  while NestrisLTM itself is down are queued by Mosquitto (persistent session).

## Hearts in the 1 vs 1 (*Matches*)

Once the bracket is fixed (*Turnier* → FIX), every match between two players
is played for hearts: both start with 2 (admin page *Matches* → *Herzen pro
Spieler*; per match e.g. 3 for the final). The loser of a round loses a heart;
a tie costs nobody one. At 0 hearts the opponent is set as the winner in the
bracket (kiosk, console and overlays update); giving the heart back removes
that winner again. FIX, reset and unseed start all hearts over.

- *Matches*: − / + per player, hearts per match, history with *Rückgängig*.
- *Verlierer automatisch erkennen* (off by default): when both players of a
  pair finished their game, the lower score loses a heart at once (tie:
  nobody); undo it in the history. Every pair of a scene plays its own
  rounds (`2x1v1`: top and bottom match separately; *Neue Runde 1/2* and
  *3/4* on *Szenen*, `POST /api/scenes/<scene>/rounds?group=0|1`).
- Overlays (`1v1`, `2x1v1`) show the hearts of the match bound to each pair
  of the scene. *Szenen*: per pair *Match* = automatic (the cards on the two
  stations belong to the two players of an open match) or chosen by hand (a
  manual choice always wins).

### Stream Deck

Create an API token with the scope `control` (*Einstellungen* → API-Tokens).
Every request sends it as the header `Authorization: Bearer <token>`. The
URLs name the scene and the slot (slot 0 = left player of the first pair):

| Request | Effect |
|---|---|
| `POST /api/control/scenes/<scene>/slots/<slot>/lives/lose` | take a heart |
| `POST …/lives/gain` | give one back |
| `POST …/lives/set/<n>` | set to n (idempotent) |
| `POST …/lives/cycle` | 2 → 1 → 0 → 2 |
| `POST …/lives/undo` | undo the last change of that match |
| `GET  …/lives` | `{"player", "lives", "max", "winner_id", …}` |

**Recommended: the action *NestrisLTM Herzen*** of the Retroverse plugin
(`StreamDeck/multistagebutton`, from version 0.2): one key per player,
settings NestrisLTM address, token, scene and slot. The key shows the
player's name and pixel hearts as NestrisLTM has them (polled every second,
so it never drifts), *RAUS*/*SIEG* when the match is decided, and a short
message on problems (`kein Match`, `Token?`, `offline`). Short press: 2 → 1
→ 0 → 2; long press (0.6 s): undo the last change.

Alternatively the *Multi Stage Button* / *3 Stage Button* of the same plugin
(the 2/3/4-stage variants work since version 0.2): three stages titled
`♥♥`, `♥`, `–`, each with an HTTP action (`POST`, the header above): stage
1 → `…/lives/set/2`, stage 2 → `…/lives/set/1`, stage 3 → `…/lives/set/0`.
Each stage sets a fixed value, so the count is never wrong; the key's
picture can differ when hearts were changed elsewhere.

Next round from the Stream Deck: `POST /api/control/scenes/<scene>/rounds`
(`?group=0|1` for one pair of a `2x1v1` scene). `409` = no match bound to
that pair yet.

### Camera layouts (16:9)

`1v1_cam` and `2x1v1_cam` keep transparent areas for the player cameras:
camera | stats | board ‖ board | stats | camera, name and hearts above each
camera; `2x1v1_cam` gives every player a quadrant (top pair, bottom pair).
In OBS put the camera sources *below* the browser source, positioned in
those areas (*Szenen* → *Rahmen für Kamerabereiche zeigen* draws frames around them).

### NES style

*Szenen* → *Stil* → *NES (wie NestrisChamps)* (or `?style=nes` in the URL)
gives every layout the NES look: pixel font, black boxes with the NES frame,
numbers like `181,290`, the game's HUD words (LINES, LV, NEXT, TRT, DRT),
green lead / red deficit. Best with `1v1_cam` and `2x1v1_cam`. The font is
"Press Start 2P" (bundled, SIL Open Font License). If the font
"NES Tetris" is installed on the PC that runs OBS, the overlay uses it
instead; it is not shipped with NestrisLTM because its licence allows
non-commercial use only.

## Command line (`nestris-ltm.exe` in the install folder)

```text
nestris-ltm.exe check                     # database, broker, HTTP port (exit code 0 = all OK)
nestris-ltm.exe configure --db-password <pw> [--db-host H --db-port P --db-user U --db-name N]
                          [--mqtt-host H --mqtt-port P --http-port P]
nestris-ltm.exe autostart on|off|status
nestris-ltm.exe set-admin-password <name> # create an admin or reset its password
nestris-ltm.exe migrate                   # create/upgrade the database, then exit
nestris-ltm.exe config-path
nestris-ltm.exe --headless                # core without GUI (console)
nestris-ltm.exe simulate game.ngf.gz --stations station-1 --names Max
NestrisLTM.exe [--minimized]              # tray app
```

## Files

| What | Where |
|---|---|
| Program | `C:\Program Files\NestrisLTM` |
| Configuration | `%APPDATA%\NestrisLTM\config.toml` (all keys: [config.example.toml](../config.example.toml)); contains the database password |
| Logs | `%APPDATA%\NestrisLTM\logs\nestris-ltm.log` (rotating) |
| Event spool | `%APPDATA%\NestrisLTM\spool\` (results not yet in the database) |
| Database | PostgreSQL data directory, e.g. `C:\Program Files\PostgreSQL\18\data` |
| Mosquitto | `C:\Program Files\mosquitto\mosquitto.conf`, data and log in `C:\ProgramData\mosquitto\` |

## Updates

NestrisLTM checks `github.com/oe7set/nestris-ltm` for new releases one minute
after the start and then daily (`[updates]` in the config; offline is fine).
A new version shows up as a tray balloon and on the admin page *Updates*:

1. *Updates* → read the release notes → *Version x.y.z installieren*.
2. NestrisLTM downloads the installer, checks the **signature** of the
   release (only releases signed with the Retroverse release key are
   accepted) and the installer's checksum,
3. backs up the database with `pg_dump` to `%APPDATA%\NestrisLTM\backups\`
   (the last 10 are kept),
4. starts the installer (Windows asks for admin rights once), quits, and
   the installer starts NestrisLTM again.

If games are running, the page asks first; results sent meanwhile are
queued by Mosquitto and the stations. *Andere Version …* installs an older
release (rollback); if the newer version changed the database, restore its
backup (below) after going back. Installing only works in the installed app,
not when started from source.

### Stations, readers and terminals (*Geräte*)

The admin page *Geräte* lists every station (package version, reader
firmware) and every terminal (app version, reader firmware) next to the
newest releases of `nestris-core`, `nestris-rfid-reader` and
`nestris-terminal`.

- *Station aktualisieren* / *Leser aktualisieren*: NestrisLTM downloads the
  release (this PC needs internet once; the stations do not), verifies it
  and sends the station an update command. The station downloads the files
  from NestrisLTM, checks the signature again, installs and restarts
  (station) or flashes the reader over USB. Progress appears in the table.
  The station needs `[host] url` and a token with the scope `stations` (as
  for the recording upload); reader updates need `esptool` on the station
  (`sudo apt install esptool`).
- Not while a game runs on that station (both sides refuse).
- Terminals update themselves: hidden menu → *Updates* on the touch PC.
- Downloaded releases stay in `%APPDATA%\NestrisLTM\release-cache\`
  (delete the folder to free space).

## Backup and restore

All tournament data is in the PostgreSQL database. Back it up before and
after every event day:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -U postgres -Fc -f "D:\Backup\nestrisltm-$(Get-Date -f yyyyMMdd-HHmm).dump" nestrisltm
```

Restore into an empty database (NestrisLTM stopped):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres nestrisltm
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -U postgres -d nestrisltm "D:\Backup\nestrisltm-....dump"
```

Old events stay in the database; the active event's time window decides
what the views show.

## Security

- The admin UI needs a login; write APIs need tokens; overlays and displays
  are read-only and open on the LAN.
- The firewall rules allow ports 7990 and 1883 from the **local subnet**
  only. Run the tournament on its own network; do not forward these ports.
- Mosquitto accepts anonymous clients. On a shared network create MQTT users
  (see the comments in `mosquitto.conf`) and set `[mqtt] username/password`
  in the NestrisLTM config and the stations.

## Troubleshooting

| Symptom | Check |
|---|---|
| Tray icon orange, *Datenbank* red | `nestris-ltm.exe check`. Service *postgresql-x64-18* running (`services.msc`)? Password in the config right (`configure --db-password`)? |
| Tray icon orange, *MQTT* red | Service *Mosquitto Broker* running? `C:\ProgramData\mosquitto\mosquitto.log`. A config error stops the service: compare with `packaging\mosquitto\mosquitto.conf`. |
| Tray icon red / window says port in use | Another program (or a second NestrisLTM under another user) uses 7990: `check` names it; change `--http-port`. |
| Stations do not appear | Station `[mqtt] host` = host IP, same `topic_prefix`, firewall rule for 1883, both PCs in the same subnet. |
| Recordings missing after a game | Station `[host]` URL and token (scope `stations`), firewall rule for 7990; the station retries uploads from its queue. |
| Other PCs cannot open the admin UI | Firewall rule *NestrisLTM (HTTP)*; Windows marks the network as *Public*? The rule covers all profiles but only the local subnet. |

## Building (developers)

```powershell
winget install JRSoftware.InnoSetup      # once
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Results: `dist\NestrisLTM\` (`NestrisLTM.exe` tray app, `nestris-ltm.exe`
CLI) and `dist\NestrisLTM-Setup-<version>.exe`. The version comes from
`pyproject.toml`; a tag `v<version>` on GitHub builds the release (see
`.github/workflows/release.yml`).

**Updating the bundled PostgreSQL/Mosquitto versions:** change `PgUrl` /
`MqUrl` in `packaging/installer.iss` and set `PgSha256` / `MqSha256` to the
SHA-256 of the new files (`Get-FileHash <file> -Algorithm SHA256`). The
PostgreSQL installer is signed by EnterpriseDB; the Mosquitto installer is
not signed upstream, so its pinned hash is the only integrity check.
