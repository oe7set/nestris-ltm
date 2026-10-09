# Changelog

The section of a version is the text of its GitHub release and what the
built-in updater shows before installing (`.github/scripts/release_notes.py`).

## 0.3.0

- **Station configuration from here** (*Stationen & Geräte* →
  *Konfiguration*, stations 0.3.0+): a template for all stations plus
  per-station values (capture size and rate, recognition size, region,
  game-detection thresholds, live rate, recordings, reader). Saving sends
  them; the station applies them after the running game and reports
  *übernommen*, *wartet auf Spielende* or *abgelehnt* with the reason.
  Device suggestions via *Geräte suchen*; values pinned on the station are
  shown as locked.
- **Station performance** (*Stationen & Geräte* → *Leistung*): camera and
  recognition FPS, dropped and missing frames, engine time, CPU, and how
  many live messages arrive here (losses, latency), with a 15-minute history.
  The dashboard's FPS column shows a traffic light.
- **The scene flow follows the tournament**: before FIX every scene shows
  the current game of each station (qualifying), FIX switches them to
  rounds with hearts and starts round 1 fresh, UNSEED goes back. Per scene
  it can be set to *always qualifying* or *always rounds*; whether the next
  round starts by itself is one global switch.
- **New page *Regie*** (control room) replaces *Szenen* and *Matches*: the
  phase with FIX, per scene flow and mode, the live slots with hearts − / +,
  the match per pair, next round, reset slot.
- **Tournament phase everywhere**: a banner on *Regie*, *Turnier* and the
  dashboard shows qualifying or fixed, with FIX / UNSEED right there.
- ***Turnier*** has the tabs *Turnierbaum* (the console) and *Matches &
  Herzen*.
- ***Einstellungen*** has tabs: *Turnier & Szenen* (hearts defaults, also
  before FIX; next round), *Highscore-Anzeige* (font size, autoscroll,
  effects, banners, transparency, celebration, scroll, addresses; moved out
  of the tournament console) and *Zugang* (admins, tokens).
- ***Stationen & Geräte*** is one page with the tab *Versionen & Updates*.
- Scene export is look-only again (no flow or mode).

## 0.2.1

- **Qualifying scenes**: a scene's flow can be *Quali*: every slot always
  shows the current game of its station (board, score, stats, difference);
  after game over the result stays until the next game starts there. No
  rounds, no hearts; the overlay shows QUALI instead of the round.

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
  (`1v1_cam`, `2x1v1_cam`); pixel hearts; the NES style like NestrisChamps
  is the standard for every scene.
- **Scene studio**: gallery with live preview images, an editor with a large
  live preview (style, colours, blocks, stations), duplicate, guide lines,
  export/import of the look of scenes (no stations or names).
- **Layout builder**: own overlay layouts by drag and drop on 1920×1080, from
  a template or blank (snapping, align, layers, mirror a player, undo/redo);
  they work like the built-in layouts (pairs, rounds, hearts).
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
