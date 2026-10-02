"""The desktop shell: tray icon, main window, core lifecycle.

    QApplication (main thread)          CoreThread
    ├─ InstanceServer  <── 2nd start     └─ Runtime.serve()  (asyncio loop:
    ├─ QSystemTrayIcon (status, menu)        HTTP, MQTT ingest, workers)
    └─ MainWindow (QWebEngineView -> http://127.0.0.1:<port>/)

The window hides on close; "Beenden" in the tray menu stops the core
(flushing buffered frames) and exits.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog
from PySide6.QtCore import QTimer, QtMsgType, QUrl, qInstallMessageHandler
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from nestris_ltm import __version__
from nestris_ltm.config import Settings
from nestris_ltm.runtime import Runtime
from nestris_ltm.shell import autostart
from nestris_ltm.shell.core_thread import CoreThread
from nestris_ltm.shell.icon import Health, app_icon, tray_icon
from nestris_ltm.shell.single_instance import InstanceServer, send_to_running, server_name
from nestris_ltm.shell.window import MainWindow

log = structlog.get_logger(__name__)

APP_USER_MODEL_ID = "Retroverse.NestrisLTM"
STATUS_INTERVAL_MS = 2000


def _qt_message_handler(mode: QtMsgType, _context: object, message: str) -> None:
    level = {
        QtMsgType.QtDebugMsg: "debug",
        QtMsgType.QtInfoMsg: "info",
        QtMsgType.QtWarningMsg: "warning",
    }.get(mode, "error")
    getattr(structlog.get_logger("qt"), level)(message)


def _set_app_user_model_id() -> None:
    # Groups the taskbar button under our icon instead of python.exe's.
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


class ShellApp:
    def __init__(
        self, app: QApplication, settings: Settings, config_path: Path, minimized: bool
    ) -> None:
        self.app = app
        self.settings = settings
        self.config_path = config_path
        self.runtime = Runtime(settings)
        self.core = CoreThread(self.runtime)
        self.window = MainWindow(self.runtime.local_url, self.runtime.shell_token)
        self.tray = QSystemTrayIcon(tray_icon(Health.STARTING), app)
        self._health: Health | None = None
        self._told_about_tray = False
        self._quitting = False
        self._start_minimized = minimized

        self._build_tray()
        self.window.hidden_to_tray.connect(self._on_hidden_to_tray)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # Without a tray a hidden window could never come back: close = quit.
            self.window.hidden_to_tray.connect(self.quit)
        # Windows logoff/shutdown ends the event loop without our menu.
        app.aboutToQuit.connect(self._stop_core_on_exit)

        self._status_timer = QTimer(app)
        self._status_timer.timeout.connect(self._refresh_status)

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self.core.start()
        self.tray.show()
        if not self._start_minimized:
            self.window.bring_to_front()
        self._status_timer.start(STATUS_INTERVAL_MS)
        QTimer.singleShot(200, self._refresh_status)

    def handle_command(self, command: str) -> None:
        if command == "show":
            self.show_window()
        elif command == "quit":
            self.quit()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        log.info("shutting down")
        self._status_timer.stop()
        self.tray.setToolTip("NestrisLTM wird beendet …")
        self.window.hide()
        if not self.core.stop(timeout_s=15.0):
            log.warning("core did not stop in time")
        self.tray.hide()
        self.app.quit()

    def _stop_core_on_exit(self) -> None:
        if not self._quitting:
            self._quitting = True
            self.core.stop(timeout_s=10.0)

    # ------------------------------------------------------------ tray

    def _build_tray(self) -> None:
        menu = QMenu()
        self._open_action = QAction("Öffnen", menu)
        self._open_action.triggered.connect(self.show_window)
        menu.addAction(self._open_action)

        browser = QAction("Im Browser öffnen", menu)
        browser.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(self.runtime.local_url)))
        menu.addAction(browser)

        diagnostics = QAction("Diagnose (JSON)", menu)
        diagnostics.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.runtime.local_url + "/api/diagnostics"))
        )
        menu.addAction(diagnostics)

        logs = QAction("Log-Ordner öffnen", menu)
        logs.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.settings.log_dir)))
        )
        menu.addAction(logs)

        menu.addSeparator()
        self._autostart_action = QAction("Mit Windows starten", menu, checkable=True)
        self._autostart_action.setEnabled(autostart.is_supported())
        self._autostart_action.setChecked(autostart.is_enabled())
        self._autostart_action.toggled.connect(self._toggle_autostart)
        menu.addAction(self._autostart_action)

        menu.addSeparator()
        quit_action = QAction("Beenden", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self._menu = menu  # keep a reference; Qt does not own it via the tray
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(f"NestrisLTM {__version__}")
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def _toggle_autostart(self, enabled: bool) -> None:
        try:
            autostart.set_enabled(enabled, self.config_path)
        except OSError as exc:
            log.error("autostart change failed", error=repr(exc))
            QMessageBox.warning(
                None, "NestrisLTM", f"Autostart konnte nicht geändert werden:\n{exc}"
            )
            self._autostart_action.blockSignals(True)
            self._autostart_action.setChecked(autostart.is_enabled())
            self._autostart_action.blockSignals(False)
        else:
            log.info("autostart changed", enabled=enabled)

    def _on_hidden_to_tray(self) -> None:
        if not self._told_about_tray and self.tray.supportsMessages():
            self.tray.showMessage(
                "NestrisLTM läuft weiter",
                "Das Programm läuft im Hintergrund weiter. Beenden über das Tray-Symbol.",
                app_icon(),
                4000,
            )
            self._told_about_tray = True

    def show_window(self) -> None:
        self.window.bring_to_front()

    # ------------------------------------------------------------ status

    def _refresh_status(self) -> None:
        rt = self.runtime
        if self.core.finished.is_set():
            self._set_health(Health.DOWN)
            error = self.core.error or "Kern wurde beendet"
            self.tray.setToolTip(f"NestrisLTM: Fehler\n{error}")
            self.window.show_message(f"NestrisLTM konnte nicht starten:\n\n{error}")
            if not self._quitting:
                self._status_timer.stop()
                self.window.bring_to_front()
            return
        if not rt.http_started:
            self._set_health(Health.STARTING)
            return
        if not self.window.loaded:
            self.window.load_app("/")

        db_ok = rt.db.is_ready
        mqtt_ok = rt.mqtt.connected or not rt.settings.mqtt.enabled
        stations = rt.hub.stations()
        now = datetime.now(UTC)
        online = sum(1 for s in stations if s.online(now))
        self._set_health(Health.OK if db_ok and mqtt_ok else Health.DEGRADED)
        self.tray.setToolTip(
            "\n".join(
                [
                    f"NestrisLTM {__version__}",
                    f"Datenbank: {'ok' if db_ok else 'nicht verbunden'}",
                    f"MQTT: {'verbunden' if rt.mqtt.connected else 'nicht verbunden'}",
                    f"Stationen online: {online}/{len(stations)}",
                ]
            )
        )

    def _set_health(self, health: Health) -> None:
        if health is not self._health:
            self._health = health
            self.tray.setIcon(tray_icon(health))


def run_shell(settings: Settings, config_path: Path, *, minimized: bool = False) -> int:
    _set_app_user_model_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("NestrisLTM")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    qInstallMessageHandler(_qt_message_handler)

    # A second start just brings the running instance to the front.
    instance_name = server_name(settings.http.port)
    if send_to_running("show", instance_name):
        log.info("already running, activated the existing instance")
        return 0
    server = InstanceServer(instance_name)
    if not server.listen():
        log.warning("single-instance server could not listen; continuing anyway")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("no system tray available; the window cannot hide to the tray")
        minimized = False

    shell = ShellApp(app, settings, config_path, minimized)
    server.command_received.connect(shell.handle_command)
    app.aboutToQuit.connect(server.close)
    shell.start()
    return app.exec()
