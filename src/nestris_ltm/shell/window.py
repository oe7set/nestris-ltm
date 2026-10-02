"""Main window: an embedded browser showing the admin UI.

Closing the window only hides it; the app keeps running in the tray. The
embedded browser sends the runtime's shell token with every request to the
local server, which grants an admin session without a login.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QMainWindow, QStackedWidget

from nestris_ltm.shell.icon import app_icon

SHELL_TOKEN_HEADER = b"X-NestrisLTM-Shell-Token"


class ShellTokenInterceptor(QWebEngineUrlRequestInterceptor):
    """Adds the shell token header to requests for the local server only."""

    def __init__(self, origin: QUrl, token: str) -> None:
        super().__init__()
        self._origin = origin
        self._token = token.encode("ascii")

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl()
        if url.host() == self._origin.host() and url.port() == self._origin.port():
            info.setHttpHeader(SHELL_TOKEN_HEADER, self._token)


class _Page(QWebEnginePage):
    """Opens links to other sites in the system browser instead of the app."""

    def __init__(self, profile: QWebEngineProfile, origin: QUrl) -> None:
        super().__init__(profile)
        self._origin = origin

    def acceptNavigationRequest(
        self, url: QUrl | str, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool
    ) -> bool:
        url = QUrl(url)
        if is_main_frame and url.host() != self._origin.host():
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class MainWindow(QMainWindow):
    hidden_to_tray = Signal()

    def __init__(self, base_url: str, shell_token: str) -> None:
        super().__init__()
        self.setWindowTitle("NestrisLTM")
        self.setWindowIcon(app_icon())
        self.resize(1280, 820)
        self._base = QUrl(base_url)

        # A named, off-the-record profile keeps this browser separate from
        # any other QtWebEngine user and stores nothing on disk.
        self._profile = QWebEngineProfile(self)
        self._interceptor = ShellTokenInterceptor(self._base, shell_token)
        self._profile.setUrlRequestInterceptor(self._interceptor)

        self._view = QWebEngineView(self)
        self._view.setPage(_Page(self._profile, self._base))

        self._placeholder = QLabel("NestrisLTM startet …")
        self._placeholder.setStyleSheet(
            "background:#0b1020;color:#cbd5e1;font-size:18px;qproperty-alignment:AlignCenter;"
        )
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._view)
        self.setCentralWidget(self._stack)
        self._loaded = False

    def show_message(self, text: str) -> None:
        self._placeholder.setText(text)
        self._stack.setCurrentWidget(self._placeholder)

    def load_app(self, path: str = "/") -> None:
        self._view.setUrl(self._base.resolved(QUrl(path)))
        self._stack.setCurrentWidget(self._view)
        self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        # Close = hide to tray; quitting goes through the tray menu.
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()
