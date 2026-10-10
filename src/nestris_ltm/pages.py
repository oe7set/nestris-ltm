# ruff: noqa: E501, RUF001  (descriptions read better unwrapped)
"""Registry of every page, view and endpoint NestrisLTM offers.

The admin UI's overview page renders this list, so a new page only has to
be registered here to show up there (with its URL, purpose and status).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Group = Literal["admin", "display", "overlay", "diagnostics", "api", "tray"]
Status = Literal["available", "planned"]


@dataclass(frozen=True, slots=True)
class PageInfo:
    id: str
    group: Group
    path: str  # URL path, or a tray menu label for group "tray"
    title_de: str
    title_en: str
    description_de: str
    description_en: str
    public: bool = False  # reachable without login (OBS, kiosk screens)
    status: Status = "available"
    phase: int | None = None  # roadmap phase for planned entries

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PAGES: tuple[PageInfo, ...] = (
    # ------------------------------------------------------------ admin UI
    PageInfo("dashboard", "admin", "/#/", "Dashboard", "Dashboard",
             "Live-Status: Datenbank, Broker, Stationen, laufende Spiele, Log.",
             "Live status: database, broker, stations, running games, log."),
    PageInfo("players", "admin", "/#/players", "Spieler", "Players",
             "Spieler suchen, anlegen, bearbeiten, zusammenführen, Karten verwalten, pro Event ausblenden; mehrere auf einmal löschen/wiederherstellen; auch am Handy.",
             "Search, create, edit and merge players, manage cards, hide per event; delete/restore several at once; works on phones."),
    PageInfo("games", "admin", "/#/games", "Spiele", "Games",
             "Alle Spiele mit Filtern (Event, Station, nicht zugeordnet, Cheat, ungültig), bearbeiten, anlegen, ausblenden; Mehrfachauswahl zum Löschen, Aus-/Einblenden und Zuweisen; auch am Handy.",
             "All games with filters (event, station, unassigned, cheat, invalid); edit, create, hide; multi-select to delete, hide/show and assign; works on phones."),
    PageInfo("events", "admin", "/#/events", "Events", "Events",
             "Events mit Zeitfenster anlegen und aktivieren; nur Spiele im Fenster des aktiven Events zählen.",
             "Create and activate events; only games inside the active event's window count."),
    PageInfo("stations", "admin", "/#/stations", "Stationen & Geräte", "Stations & devices",
             "Capture-Stationen mit Live-Zustand (umbenennen, pro Event ausblenden, entfernen); Tab Versionen & Updates: Stationen, Terminals und Kartenleser mit Version, Stationen und Leser per Klick aktualisieren.",
             "Capture stations with live state (rename, hide per event, remove); tab versions & updates: stations, terminals and card readers with their versions, update stations and readers with one click."),
    PageInfo("audit", "admin", "/#/audit", "Protokoll", "Audit log",
             "Wer hat wann was geändert (vorher/nachher).",
             "Who changed what and when (before/after)."),
    PageInfo("settings", "admin", "/#/settings", "Einstellungen", "Settings",
             "Tabs: Allgemein (Sprache), Turnier & Szenen (neue Runde automatisch, Herzen-Standards), Highscore-Anzeige (Schriftgröße, Autoscroll, Effekte, Meldungen, Transparenz, Celebration, Scroll, Adressen), Zugang (Admins, API-Tokens).",
             "Tabs: general (language), tournament & scenes (automatic next round, hearts defaults), highscore display (font size, autoscroll, effects, banners, transparency, celebration, scroll, addresses), access (admins, API tokens)."),
    PageInfo("updates", "admin", "/#/updates", "Updates", "Updates",
             "Nach neuen Versionen suchen (GitHub), Versionshinweise lesen, per Klick installieren (mit Datenbank-Sicherung), ältere Version wählen.",
             "Look for new versions (GitHub), read release notes, install with one click (with a database backup), pick an older version."),
    PageInfo("database", "admin", "/#/database", "Datenbank", "Database",
             "Zustand der Datenbank mit Erklärung und Lösungsschritten (erscheint von selbst, wenn sie nicht nutzbar ist); Verbindung testen und ändern, Backups erstellen und wiederherstellen (am Host-PC).",
             "Database state with explanation and solution steps (shown by itself when it is not usable); test and change the connection, create and restore backups (on the host PC)."),
    PageInfo("pages", "admin", "/#/pages", "Übersicht", "Overview",
             "Diese Seite: alle Seiten, Anzeigen, Overlays und Schnittstellen.",
             "This page: every page, display, overlay and interface."),
    PageInfo("tournament", "admin", "/#/tournament", "Turnier", "Tournament",
             "Phase (Quali / fixiert) mit FIX/UNSEED; Tab Turnierbaum: Größe, Sieger per Klick, Spieler aus dem Baum nehmen; Tab Matches & Herzen: Herzen pro Match, Verlauf mit Rückgängig.",
             "Phase (qualifying / fixed) with FIX/UNSEED; tab bracket: size, click winners, remove players; tab matches & hearts: hearts per match, history with undo."),
    PageInfo("regie", "admin", "/#/regie", "Regie", "Control room",
             "Alles im Turnierbetrieb: Phase mit FIX, Ablauf je Szene (automatisch nach Turnierphase / immer Quali / immer Runden), neue Runde, Slot zurücksetzen, Herzen −/+ am Spieler, Match je Paar, OBS-Adressen.",
             "Everything during the event: phase with FIX, flow per scene (automatic by tournament phase / always qualifying / always rounds), next round, reset slot, hearts −/+ per player, match per pair, OBS addresses."),
    PageInfo("studio", "admin", "/#/studio", "Szenen-Studio", "Scene studio",
             "Szenen mit Vorschaubildern gestalten (Stil, Farben, Bausteine), duplizieren, das Aussehen exportieren/importieren; eigene Layouts im Baukasten bauen.",
             "Design scenes with preview images (style, colours, blocks), duplicate them, export/import their look; build own layouts in the layout builder."),
    PageInfo("studio-layout", "admin", "/#/studio/layout/new", "Layout-Baukasten", "Layout builder",
             "Elemente frei auf 1920×1080 anordnen (Einrasten, Ausrichten, Spiegeln, Ebenen, Rückgängig), aus Vorlage oder leer; als eigenes Layout speichern.",
             "Place elements freely on 1920×1080 (snapping, align, mirror, layers, undo), from a template or blank; save as an own layout."),
    # ------------------------------------------------------------ public displays
    PageInfo("kiosk", "display", "/view/highscore", "Highscore + Turnierbaum", "Highscore + bracket",
             "Vollbild-Anzeige mit allen Animationen (Flug-Animationen, Score-Train, Meldungen, Sieger-Feier). Auch für OBS geeignet.",
             "Full-screen display with all animations (flights, score train, banners, champion celebration). Works in OBS too.",
             public=True),
    PageInfo("kiosk-highscore", "display", "/view/highscore?only=highscore", "Nur Highscore", "Highscore only",
             "Nur die Highscore-Spalte, volle Breite.", "Only the highscore column, full width.", public=True),
    PageInfo("kiosk-bracket", "display", "/view/highscore?only=bracket", "Nur Turnierbaum", "Bracket only",
             "Nur der Turnierbaum, volle Breite. Mit &transparent=1 ohne Hintergrund für OBS.",
             "Only the bracket, full width. Add &transparent=1 for a transparent OBS background.", public=True),
    PageInfo("tournament-console", "display", "/view/tournament-admin", "Turnierkonsole (Vollbild)", "Tournament console (full screen)",
             "Die Turniersteuerung als eigene Seite, z. B. auf einem Tablet.",
             "The tournament control as a page of its own, e.g. on a tablet."),
    # ------------------------------------------------------------ OBS overlays
    PageInfo("overlay-scene", "overlay", "/o/<szene>", "Overlay je Szene", "Overlay per scene",
             "Feste OBS-Browserquelle (1920×1080, transparent) je Szene. Layouts: Einzel, Einzel kompakt, 1 gegen 1, 2 × 1 gegen 1, 4 Spieler. Optionen: ?bg=dark, ?lang=en.",
             "Fixed OBS browser source (1920×1080, transparent) per scene. Layouts: single, single compact, 1 vs 1, 2 × 1 vs 1, 4 players. Options: ?bg=dark, ?lang=en.",
             public=True),
    PageInfo("overlay-round", "api", "/api/scenes/<szene>/rounds", "Neue Runde (Stream Deck)", "New round (Stream Deck)",
             "POST mit API-Token (Recht „scenes“) startet die nächste Runde einer Szene, z. B. per Stream-Deck-Taste.",
             "POST with an API token (scope “scenes”) starts the next round of a scene, e.g. from a Stream Deck button."),
    PageInfo("api-recording", "api", "/api/games/<id>/recording", "Aufzeichnung (NGF)", "Recording (NGF)",
             "Ein Spiel als NestrisChamps-NGF (gzip), z. B. für NestrisChamps oder den Replay-Viewer von nestris-core. ?download=true speichert die Datei.",
             "A game as NestrisChamps NGF (gzip), e.g. for NestrisChamps or nestris-core's replay viewer. ?download=true saves the file.",
             public=True),
    PageInfo("api-station-upload", "api", "/api/stations/<station>/games/<game_id>/ngf", "Aufnahme-Upload der Stationen", "Station recording upload",
             "PUT von nestris-station nach jedem Spiel (API-Token mit Recht „stations“).",
             "PUT from nestris-station after every game (API token with the “stations” scope)."),
    PageInfo("ws-scene", "api", "/ws/scene/<szene>", "WebSocket Szene", "WebSocket scene",
             "Zustand einer Szene plus Live-Frames (60 Hz) der Slots.",
             "A scene's state plus the slots' live frames (60 Hz).", public=True),
    # ------------------------------------------------------------ diagnostics
    PageInfo("status", "diagnostics", "/status", "Statusseite", "Status page",
             "Einfache Statusseite für Diagnosen, auch ohne gebaute Admin-Oberfläche.",
             "Plain status page for troubleshooting, works without the admin UI build."),
    PageInfo("health", "diagnostics", "/api/health", "Health", "Health",
             "Läuft der Server, ist die Datenbank verbunden (JSON).",
             "Is the server up, is the database connected (JSON)."),
    PageInfo("diagnostics", "diagnostics", "/api/diagnostics", "Diagnose (JSON)", "Diagnostics (JSON)",
             "Broker, Datenbank, Zähler, Warteschlange und alle Stationen als JSON.",
             "Broker, database, counters, spool and all stations as JSON."),
    PageInfo("db-status", "diagnostics", "/api/db/status", "Datenbank-Diagnose (JSON)", "Database diagnosis (JSON)",
             "Zustand, Fehler, Versuche, Schema-Version und Verbindung (ohne Passwort); am Host-PC auch ohne Login.",
             "State, error, attempts, schema version and connection (without password); on the host PC without login."),
    PageInfo("logs", "diagnostics", "/api/diagnostics/logs", "Log (JSON)", "Log (JSON)",
             "Letzte Log-Einträge; ?after_id=&level= zum Filtern.",
             "Recent log records; filter with ?after_id=&level=."),
    # ------------------------------------------------------------ interfaces
    PageInfo("ws-kiosk", "api", "/ws/kiosk", "WebSocket Highscore/Turnier", "WebSocket highscore/tournament",
             "Highscore, Statistik, Score-Train, Turnierbaum und Anzeige-Einstellungen live (TournamentHigscore-Protokoll).",
             "Highscore, stats, score train, bracket and display settings live (TournamentHigscore protocol).",
             public=True),
    PageInfo("ws-live", "api", "/ws/live", "WebSocket Live-Feed", "WebSocket live feed",
             "Snapshot aller Stationen, danach station-, live- und game_event-Nachrichten.",
             "Snapshot of all stations, then station, live and game_event messages.",
             public=True),
    PageInfo("api-docs", "api", "/docs", "API-Dokumentation", "API documentation",
             "Alle REST-Schnittstellen interaktiv (OpenAPI).",
             "Every REST endpoint, interactive (OpenAPI)."),
    PageInfo("api-terminal", "api", "/api/terminal/v1", "Terminal-API", "Terminal API",
             "Schnittstelle des Spieler-Terminals (nestris-terminal): Karte prüfen, anmelden, Spielerseite, Score eintragen, Highscore. API-Token mit Recht „terminal“.",
             "Interface of the player terminal (nestris-terminal): card lookup, registration, player page, self-reported scores, highscore. API token with the “terminal” scope."),
    # ------------------------------------------------------------ tray menu
    PageInfo("tray-open", "tray", "Öffnen", "Öffnen", "Open",
             "Holt das Fenster nach vorne (auch: Doppelklick aufs Tray-Symbol).",
             "Brings the window to the front (also: double-click the tray icon)."),
    PageInfo("tray-database", "tray", "Datenbankproblem anzeigen …", "Datenbankproblem anzeigen …", "Show database problem …",
             "Nur sichtbar, wenn die Datenbank nicht nutzbar ist: öffnet das Fenster mit Erklärung und Lösung.",
             "Only shown while the database is not usable: opens the window with explanation and fix."),
    PageInfo("tray-browser", "tray", "Im Browser öffnen", "Im Browser öffnen", "Open in browser",
             "Öffnet die Oberfläche im Standard-Browser.", "Opens the UI in the default browser."),
    PageInfo("tray-diagnostics", "tray", "Diagnose (JSON)", "Diagnose (JSON)", "Diagnostics (JSON)",
             "Öffnet die Diagnose-Daten im Browser.", "Opens the diagnostics data in the browser."),
    PageInfo("tray-logs", "tray", "Log-Ordner öffnen", "Log-Ordner öffnen", "Open log folder",
             "Öffnet den Ordner mit den Logdateien.", "Opens the folder with the log files."),
    PageInfo("tray-autostart", "tray", "Mit Windows starten", "Mit Windows starten", "Start with Windows",
             "Startet NestrisLTM bei der Windows-Anmeldung minimiert im Tray.",
             "Starts NestrisLTM minimized to the tray when you sign in to Windows."),
    PageInfo("tray-quit", "tray", "Beenden", "Beenden", "Quit",
             "Beendet NestrisLTM sauber (Fenster schließen lässt es weiterlaufen).",
             "Quits NestrisLTM cleanly (closing the window keeps it running)."),
)  # fmt: skip
