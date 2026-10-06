# Changelog

The section of a version is the text of its GitHub release and what the
built-in updater shows before installing (`.github/scripts/release_notes.py`).

## 0.2.0

First stable release of the new NestrisLTM, the host app of the Retroverse
NES Tetris tournament. It replaces the old NestrisLTM and TournamentHigscore.

- **Stations**: live data, game start/end and cheats over MQTT (durable,
  nothing is lost when the database or the app is down), recordings uploaded
  by the stations, replay of every game.
- **Admin** (Svelte, German/English): players, games (edit, assign, hide,
  manual entry, NGF import), events, stations, audit log, API tokens,
  diagnostics with live log; stay signed in.
- **Highscore and tournament**: the TournamentHigscore kiosk with all
  animations, bracket 2–64 players with byes, FIX/UNSEED.
- **Hearts in the 1 vs 1**: after FIX every match is played for hearts
  (default 2, per match adjustable); at 0 hearts the opponent advances in the
  bracket, undo at any time; optional automatic loser detection; page
  *Matches*.
- **OBS overlays**: scenes with fixed URLs, rounds with frozen scores (every
  pair of a scene plays its own rounds), layouts single, 1 vs 1, 2 × 1 vs 1,
  4 players, replay, and new 16:9 layouts with camera areas
  (`1v1_cam`, `2x1v1_cam`); pixel hearts; NES style like NestrisChamps.
- **Stream Deck**: token scope `control`, hearts and rounds per URL; the
  plugin action *NestrisLTM Herzen* shows the real hearts.
- **Player terminal API** for the Retroverse Terminal (registration, player
  page, self-reported scores).
- **Devices**: stations, terminals and card readers with versions; stations
  and their readers are updated from here (stations need no internet).
- **Updates**: checks GitHub, installs on a click after a database backup;
  only releases signed with the Retroverse key are accepted.
- **Installer**: installs or reuses PostgreSQL and Mosquitto, firewall rules,
  autostart in the tray.
