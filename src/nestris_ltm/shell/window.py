"""Main window: an embedded browser showing the admin UI.

Closing the window only hides it; the app keeps running in the tray. The
embedded browser sends the runtime's shell token with every request to the
local server, which grants an admin session without a login.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEnginePermission,
    QWebEngineProfile,
    QWebEngineSettings,
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


UrlOpener = Callable[[QUrl], object]


class _NewWindowPage(QWebEnginePage):
    """Stand-in for a new browser window (``target="_blank"``, ``window.open``).

    The embedded browser has no tabs: the first URL the "window" navigates to
    is handed to the system browser, then the stand-in deletes itself.
    """

    def __init__(self, profile: QWebEngineProfile, parent: QObject, opener: UrlOpener) -> None:
        super().__init__(profile, parent)
        self._opener = opener
        self._done = False
        # Some navigations (e.g. rel="noopener") only show up as a URL change.
        self.urlChanged.connect(self._open)

    def acceptNavigationRequest(
        self, url: QUrl | str, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool
    ) -> bool:
        self._open(QUrl(url))
        return False

    def _open(self, url: QUrl) -> None:
        if self._done or url.scheme() not in ("http", "https", "mailto"):
            return
        self._done = True
        self._opener(url)
        self.deleteLater()


class _Page(QWebEnginePage):
    """The admin UI page.

    - Links to other sites and new windows open in the system browser (the
      overlay and kiosk views are meant for OBS / other screens anyway).
    - The page may write to the clipboard ("URL kopieren" buttons).
    """

    def __init__(
        self, profile: QWebEngineProfile, origin: QUrl, opener: UrlOpener = QDesktopServices.openUrl
    ) -> None:
        super().__init__(profile)
        self._origin = origin
        self._opener = opener
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)
        self.permissionRequested.connect(self._on_permission)

    def acceptNavigationRequest(
        self, url: QUrl | str, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool
    ) -> bool:
        url = QUrl(url)
        external = url.scheme() == "mailto" or (
            url.scheme() in ("http", "https") and url.host() != self._origin.host()
        )
        if is_main_frame and external:
            self._opener(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _type: QWebEnginePage.WebWindowType) -> QWebEnginePage:
        return _NewWindowPage(self.profile(), self, self._opener)

    def _on_permission(self, permission: QWebEnginePermission) -> None:
        # Only the app's own pages, and only the clipboard.
        same_origin = permission.origin().host() == self._origin.host()
        clipboard = (
            permission.permissionType() == QWebEnginePermission.PermissionType.ClipboardReadWrite
        )
        if same_origin and clipboard:
            permission.grant()
        else:
            permission.deny()


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
        # Keep a reference: QWebEngineView.setPage() does not take ownership.
        # A temporary page is garbage-collected at once and the view silently
        # falls back to a default page (no shell token, no link/clipboard
        # handling).
        self._page = _Page(self._profile, self._base)
        self._view.setPage(self._page)

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
