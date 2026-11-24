# Changelog

The section of a version is the text of its GitHub release and what the
built-in updater shows before installing (`.github/scripts/release_notes.py`).

## 0.7.0

- **Scene studio: no more double frames.** Next piece, versus, ranking and
  diff graph of own layouts were framed twice in OBS (and in the studio,
  where it was barely visible when zoomed out). Every element with a box
  now has *Rahmen*: standard, thin line or none.
- **Text sizes no longer jump.** Scores, names, title and round are sized
  for a reserved number of characters (*Stabil*, the new default for all
  layouts), so they stay the same while scores grow or names change; only
  longer text shrinks. *Fest* takes a size in px, *An Text anpassen* is the
  old behaviour. Name tags keep the room of the hearts and no longer cut
  the name off. Several elements can be set at once.
- **Resizing**: *Verhältnis Auto / Halten / Frei* under the stage (Shift
  inverts, Ctrl from the centre), snapping can be switched off. A playfield
  can stretch to fill its box; *An Spielfeld anpassen* shrinks the box to it.
- **Linked slots**: build one player, the others follow live, mirrored or
  moved — presets *1 vs 1 gespiegelt*, *4 Viertel gespiegelt/gleich*,
  *Darunter gleich/gespiegelt* or an own link; pairs follow too.
- **Arranging**: a bar above the stage aligns to the selection, the stage,
  the key element or the frame around; distributes with equal or fixed
  gaps; lines up as row, column or grid; same width/height; select alike;
  copy/paste a style. Distances to the neighbours while dragging, snapping
  to equal gaps, Alt over an element measures, right-click menu.

## 0.6.0

- **Attract-mode demo games** (the console's demo on the title screen) no
  longer count: games from older stations that replay the known demo are
  flagged when they end or their recording arrives and are hidden from
  rankings, bracket, kiosk, player stats, exports and counts. The dashboard
  shows *Demo-Spiel* in a station's game state while the demo plays (station
  0.4.0+, which never sends demos at all) and how many demos it skipped.
- *Spiele*: filter *Demo-Spiele* (hidden / only / included), badge *Demo*,
  bulk actions *Als Demo markieren* and *Keine Demo*.
- `nestris-ltm demo-scan [--apply | --suggest --export DIR]` and
  `nestris-ltm demo-purge [--yes]` find, flag and delete the demo games
  already stored.
- Database migration 0015 (`games.is_demo`, `games.demo_reason`).

## 0.5.1

- **Terminal API** for the new card functions of the Retroverse Terminal
  (0.3.0b3): `GET /api/terminal/v1/players?q=` finds players by nickname or
  name (only nicknames are returned) to give a player a new card, and
  `DELETE /api/terminal/v1/card/{uid}` forgets a card so it counts as new
  again (the terminal's clear mode; the player keeps the games). Both are
  recorded in the audit log.

## 0.5.0

- **Scene studio rebuilt, like OBS**: one editor per scene with the
  1920 × 1080 stage in the middle, zoomed to fit; the status bar shows the
  stage size, zoom, mouse position and selection in real pixels. Ctrl +
  mouse wheel zooms, Space or the middle mouse button pans. Layers and the
  element palette on the left, properties (in px), the scene's look and its
  stations on the right, one *Speichern* for everything. ⛶ hides the admin
  menu.
- **Every standard layout can be adapted**: *Layout anpassen* gives a scene
  its own copy of the matching template (single, single compact, 1 vs 1,
  1 vs 1 with cameras, 2 × 1 vs 1, 2 × 1 vs 1 in quadrants, 4 players);
  *Auf Vorlage zurücksetzen* goes back. The templates were measured from the
  built-in layouts, so an adapted scene looks the same.
- **New scenes start from a template**, grouped by player count. New:
  *4 Spieler: alle gegen alle (Viertel)*, a quadrant per player with a
  ranking in the middle and the round modes.
- **New elements**: ranking, the stat *zum Weiterkommen*, stats and names
  without their own frame (inside a frame element, like the built-in stats
  panels).
- Duplicating a scene also copies its own layout. Database migration 0014.

## 0.4.3

- **Build**: Python is pinned to 3.13 (`.python-version`). GitHub's runners moved
  to 3.15, where the built app no longer started. 0.4.2 never left the build.
- **Flagged results wait for review**: a game the station reports with a
  failed validation or a cheat is hidden in the active event as it arrives,
  with the reason in *Spiele*. Unhiding it releases it. Hidden games no longer
  count towards a player's best score or the profile statistics.

## 0.4.1

- **Games: score filter**: *Score ab* / *Score bis* (inclusive) in the
  filters; accepts `250000`, `250.000`, `250k` or `1,5m`. The CSV export and
  previous/next game follow the filter.
- **Sorting**: click a column header in *Spiele* (start, player, score,
  lines, level, Tetris rate, duration) or *Spieler* (nickname, games, best,
  best in the event, last played; also *angelegt*) to sort, click again to
  turn the direction. On phones a sort menu with a direction button. The
  sort stays in the address, so links and reloads keep it. *Spieler* has a
  new column *Zuletzt gespielt*.
- **Portrait display** for a screen turned upright (9:16, e.g. 1080×1920):
  `/view/highscore?layout=portrait`, highscore on top, the bracket below,
  zoomed automatically so the whole tree is visible (8 to 64 players). Listed
  in the page overview and under *Einstellungen* → *Highscore-Anzeige*.

## 0.4.0

- **Database problems explained**: instead of a raw error the app shows
  what is wrong (PostgreSQL not reachable, wrong password, login rejected,
  no right to create the database, database newer than this app, failed
  update) with solution steps. On the host the connection can be tested and
  changed without a restart. A database left by a newer version blocks
  writing and offers its backups (with the schema each contains) for a
  restore; the current database is renamed, never deleted. Tray tooltip,
  status page and `nestris-ltm check` say the same.
- **Needs attention**: a bell in the menu and a dashboard card list what
  needs a look (broker down, stations gone, failed results, games without
  a player, suspected cheats, no event, new players, update), each a link
  to the fix; optional sound. New page *Fehlgeschlagene Ergebnisse* (retry
  or discard). FIX lists what is still open.
- **Games and players**: multi-select with bulk actions (delete, hide/show,
  assign, unassign; delete/restore players), undo in the message for
  reversible actions, CSV export with the current filters.
- **Phone layout**: menu button, lists as cards, foldable filters.
- **Tournament bracket**: help folded away, *Fokus* and *Vollbild*, the
  console's player list can be hidden, zoom and *FIT* for the whole tree.
- **Regie**: station state per slot, open the slot's game or assign its
  player, keys 1–9 / N / ?, hearts with undo.
- **Results** page (podium, highscore, print), CSV exports, *Event
  abschließen* (backup, exports, end, next event), automatic backups
  (optionally copied to a second folder).
- **Helper role** for the event-day crew (Regie, hearts, looking up,
  assigning); admins keep deleting and configuring. *Überall abmelden*; a
  deleted admin or an old password no longer keeps a session.
- **Audit log** filters (object, action, person, time, text) and CSV.
- Quick search (Ctrl+K), previous/next game, in-app confirmations instead
  of browser dialogs, warnings before losing unsaved edits, accessibility
  fixes.
- The database is migrated on the first start (two new revisions). Going
  back to 0.3.x afterwards shows "Datenbank ist neuer als diese App" with
  the backup from before the update to restore.

## 0.3.1

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
