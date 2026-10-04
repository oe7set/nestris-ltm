# Updates for all Retroverse apps (plan)

One update mechanism for every part of the tournament setup. Source:
**GitHub releases of `github.com/oe7set/<repo>`**. Updates are **checked
automatically and installed on click**, never on their own and never
silently in the middle of an event.

| Part | Repository | Runs on | Release asset | Installed by |
|---|---|---|---|---|
| NestrisLTM (host) | `oe7set/nestris-ltm` | host PC, Windows | `NestrisLTM-Setup-<v>.exe` | itself (admin UI / tray) |
| Player terminal | `oe7set/nestris-terminal` | touch PC, Windows | `RetroverseTerminal-Setup-<v>.exe` | itself (hidden menu) |
| Capture station | `oe7set/nestris-core` | Debian PCs | `nestris-station_<v>_<arch>.deb` | NestrisLTM admin → station updater |
| Reader firmware | `oe7set/nestris-rfid-reader` | ESP32 on USB | `nestris-rfid-reader-<v>-esp32dev-app.bin` + `-manifest.json` | terminal / station it is plugged into |

## Release convention (all repositories)

- Tag `v<semver>` (`v1.2.0`, pre-releases `v1.3.0-rc1`), matching the version
  in the project file; the release workflow refuses mismatches (already in
  place for NestrisLTM and the terminal).
- Assets named as in the table, plus
  - `SHA256SUMS.txt` – `sha256  filename` per asset,
  - `SHA256SUMS.txt.sig` – **Ed25519 signature** of `SHA256SUMS.txt`
    (base64), made in the release workflow with the secret
    `RELEASE_SIGNING_KEY`; the matching public key is compiled into every app.
- The release body (generated notes + hand-written highlights) is shown to
  the user before installing.

Why a signature: the apps download and run installers. A checksum from the
same release only protects against broken downloads; the signature also
protects against a manipulated release (e.g. a stolen GitHub session),
because the private key never leaves the repository secrets.

## Signing key

| | |
|---|---|
| Algorithm | Ed25519, raw 32-byte keys in base64 |
| **Public key** (compiled into every app) | `CQqYvIf/DIFS0ctwZaWQEK2wCdG7Oy3jN+YkF7nRgNQ=` |
| Private key | maintainer's PC: `%USERPROFILE%\.retroverse\release-signing\release-signing-key.private.txt` (created 2026-10-04) |
| GitHub | repository secret **`RELEASE_SIGNING_KEY`** (the private key's one line) in `nestris-ltm`, `nestris-terminal`, `nestris-core`, `nestris-rfid-reader` |
| Tool | `.github/scripts/sign_release.py` (same file in every repository): `sign`, `verify`, `keygen` |

- The release workflows run `sign_release.py sign dist/SHA256SUMS.txt` and
  publish `SHA256SUMS.txt.sig`; without the secret the workflow fails instead
  of publishing an unsigned release.
- **Back up the private key** (password manager / offline). It must never
  be committed. Lost key = new key pair, and every app needs an update with
  the new public key before it accepts new releases.
- Rotation: apps hold a *list* of accepted public keys. Add the new key to
  the apps first, release, then switch the secret.
- Check a release by hand:
  `uv run --script .github/scripts/sign_release.py verify SHA256SUMS.txt CQqYvIf/DIFS0ctwZaWQEK2wCdG7Oy3jN+YkF7nRgNQ=`

## Checking

- `GET https://api.github.com/repos/oe7set/<repo>/releases` (unauthenticated,
  `User-Agent` set, `If-None-Match` with the last ETag so unchanged answers
  do not count against the 60 requests/hour limit). Optional token for
  private repositories or shared IPs.
- When: 1 minute after start, then every 24 h, and on *Jetzt prüfen*.
- Channel `stable` takes the newest non-pre-release; `beta` also
  pre-releases. Drafts are ignored.
- Comparison by semver (pre-releases sort before their release).
- Offline (no internet at the venue) is normal: the check fails quietly,
  the UI shows "zuletzt geprüft: <Zeit>, keine Verbindung".

Config (each app, same keys):

```toml
[updates]
enabled = true            # automatic checks
channel = "stable"        # or "beta"
owner = "oe7set"          # GitHub user/organisation (forks)
token = ""                # optional
```

## Installing

Common steps, done by a small shared module in each app
(`updates.py` in Python, `update.rs` in Rust):

1. Download the asset and `SHA256SUMS.txt(.sig)` into `<data_dir>/updates/`
   (HTTPS, size limit 500 MB, progress reported to the UI).
2. Verify the signature, then the asset's SHA-256. Any mismatch: delete,
   report, stop.
3. App-specific installation (below). The downloaded file is deleted after a
   successful update.

### NestrisLTM

- Admin UI *Einstellungen → Updates*: installed and available version,
  release notes, *Jetzt prüfen*, *Installieren*, *Andere Version …*
  (list of the last releases, for a rollback). Tray: balloon "Update
  verfügbar", menu item *Nach Updates suchen*.
- Install guard: if games are live or a scene round is running, the button
  asks for confirmation ("Turnier läuft – trotzdem aktualisieren?").
- **Database backup first**: `pg_dump -Fc` of the NestrisLTM database into
  `<data_dir>/backups/` (pg_dump from the PostgreSQL installation found in
  the registry). The update stops if the backup fails.
- Then run `NestrisLTM-Setup-<v>.exe /SILENT /SUPPRESSMSGBOXES /NORESTART
  /update=1` (Windows asks for admin rights once) and quit; the installer
  restarts NestrisLTM when `/update=1` is given.
- Downgrades across a database migration are refused unless the backup
  from before that update is restored (the admin page explains this).

### Player terminal

- Hidden menu → new tab *Updates*: app and reader firmware, each with
  version, notes and *Installieren*. On the main menu nothing changes for
  players.
- App: `RetroverseTerminal-Setup-<v>.exe /VERYSILENT /SUPPRESSMSGBOXES
  /update=1` (per-user install, no UAC prompt on the kiosk), then quit; the
  installer restarts the kiosk.
- Reader firmware: close the reader port, flash the **app image at
  `0x10000`** (offset from the release manifest; keeps the reader's settings)
  with `esptool`, wait for `hello`, compare `fw`, reopen. Readers
  still on the v1 sketch need the factory image once (`0x0`).
- esptool is GPL-2.0-or-later: the Windows build ships it as a **separate
  program** `esptool.exe` (own PyInstaller analysis, license file next to it,
  listed in NOTICE) that the terminal runs as a child process; terminal code
  never imports it. The station's `espflash` (MIT/Apache-2.0) has no such issue.
- Implemented in `nestris-terminal/src/nestris_terminal/updates/`
  (`service.py`, `github.py`, `releases.py` = copy of `core/releases.py` here).

### Station

The station has no screen and usually no internet, so NestrisLTM drives it
(contract: `../nestris-core/docs/STATION.md`, *Updates*):

- Stations report `version`, `reader_fw` and `reader_serial` in their MQTT
  `status`. The page *Geräte* shows them next to the newest releases and
  offers *Station aktualisieren* / *Leser aktualisieren* (with a version
  choice for rollbacks).
- NestrisLTM first downloads the release files into
  `<data_dir>/release-cache/<repo>/<tag>/` and verifies signature and
  checksums (`services/devices.py`), then publishes
  `{"type":"update","target":"station"|"reader","release":"v0.3.0","version":"0.2.1"}`
  on the existing `<prefix>/<station>/cmd` topic (QoS 1). The station's
  `version` differs from the release tag: `nestris-core` releases carry the
  station package with its own version (`nestris-station_<v>-1_<arch>.deb`).
- The station downloads the files from
  `/api/stations/<station>/updates/<repo>/<tag>/<file>` (token scope
  `stations`, like the recording upload) and **verifies the signature
  itself** (`crates/nestris-station/src/update.rs`), so the host is not
  trusted. Progress: retained `<base>/update` (`downloading`, `verifying`,
  `installing`, `flashing`, `waiting`, `done`, `failed` + detail).
- Station package: the station writes `<state_dir>/updates/request`; the
  path unit `nestris-station-update.path` starts the oneshot
  `nestris-station-update.service` (root), whose helper copies the files to a
  root-only directory, verifies them again with the installed binary
  (`nestris-station verify-update`), runs `apt-get install` and restarts the
  station. The station process itself never runs as root.
- Reader: the station closes the port and runs `esptool` (Debian package,
  a separate GPL program; the plan's `espflash` crate would have added a
  large dependency for the same job), then expects `hello` with the new `fw`.
- Not during a game: both NestrisLTM and the station refuse.

### Device overview (NestrisLTM)

The page *Geräte* lists every station, terminal and reader with its version
and whether an update is available. Terminals report their version and
reader firmware in headers of their API calls (`X-Terminal-Version`,
`X-Reader-Firmware`); they update themselves (hidden menu), the page only
shows them.

## Phases

| Phase | Content |
|---|---|
| U1 ✅ | Signing key, `sign` step in all release workflows, station `.deb` (amd64 + arm64, built on Debian 12) in the `nestris-core` release, reader firmware release |
| U2 ✅ | NestrisLTM: update service (`services/updates.py`), admin page *Updates*, tray balloon + menu, `pg_dump` backup, installer `/update=1` restart |
| U3 ✅ | Terminal: update service + *Updates* tab, installer restart, reader flashing (`esptool`). Open: flashing a real reader through the updater, a real `/update=1` run of the terminal setup |
| U4 ✅ | Station: `update` command on `cmd`, signed download from the host's release cache, `.deb` updater with root helper, reader flashing (esptool); NestrisLTM *Geräte* page with station buttons, terminal versions. Open: a real Debian station end to end (CI only installs the package and exercises the helper) |
| U5 | End-to-end test: publish test releases `v0.x.y` on GitHub and update every part from one release to the next and back |

Reader firmware phases R1–R4 (`../nestris-rfid-reader/docs/ARCHITECTURE.md`)
come before U3/U4, because those flash the new firmware.
