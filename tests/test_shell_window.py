"""The embedded admin browser: new windows open in the system browser, the
page may write to the clipboard. Uses real mouse clicks (a user gesture, as
in the app) on a page served from a local HTTP server."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets")
# Offscreen: an isolated in-process clipboard (never the user's real one).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from nestris_ltm.shell.window import _Page

COPIED = "http://127.0.0.1:7990/o/main"
PAGE = f"""<!doctype html><html><body style="margin:0">
<a id="view" href="/view/highscore" target="_blank" rel="noopener"
   style="position:absolute;left:0;top:0;width:100px;height:40px;display:block">open</a>
<a id="ext" href="https://retroverse.at/"
   style="position:absolute;left:0;top:50px;width:100px;height:40px;display:block">site</a>
<button id="copy" style="position:absolute;left:0;top:100px;width:100px;height:40px"
   onclick="navigator.clipboard.writeText('{COPIED}').then(() => document.title = 'ok', e => document.title = String(e))">copy</button>
</body></html>""".encode()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def server() -> Iterator[QUrl]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield QUrl(f"http://127.0.0.1:{httpd.server_address[1]}/")
    httpd.shutdown()


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    yield app


def wait_for(app: QApplication, check: Callable[[], object], ms: int = 10_000) -> bool:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        app.processEvents()
        if check():
            return True
    return False


@pytest.fixture
def page(qapp: QApplication, server: QUrl) -> Iterator[tuple[QWebEngineView, _Page, list[str]]]:
    opened: list[str] = []
    profile = QWebEngineProfile()
    page = _Page(profile, server, opener=lambda url: opened.append(url.toString()))
    view = QWebEngineView()
    view.setPage(page)
    loaded: list[bool] = []
    page.loadFinished.connect(loaded.append)
    view.resize(400, 300)
    view.show()
    page.setUrl(server)
    assert wait_for(qapp, lambda: loaded)
    assert loaded == [True] and opened == []  # the app's own page stays in the app
    yield view, page, opened
    view.close()
    view.deleteLater()
    page.deleteLater()
    profile.deleteLater()
    qapp.processEvents()


def click(qapp: QApplication, view: QWebEngineView, x: int, y: int) -> None:
    target = view.focusProxy() or view
    QTest.mouseClick(
        target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y)
    )
    qapp.processEvents()


def test_new_window_links_open_in_the_system_browser(
    qapp: QApplication, server: QUrl, page: tuple[QWebEngineView, _Page, list[str]]
) -> None:
    view, _, opened = page
    click(qapp, view, 20, 20)  # target="_blank" to the app's own host
    assert wait_for(qapp, lambda: opened), "new window was not handed to the system browser"
    assert opened == [server.resolved(QUrl("/view/highscore")).toString()]
    click(qapp, view, 20, 70)  # plain link to another site
    assert wait_for(qapp, lambda: len(opened) == 2)
    assert opened[1] == "https://retroverse.at/"


def test_page_may_write_the_clipboard(
    qapp: QApplication, page: tuple[QWebEngineView, _Page, list[str]]
) -> None:
    _, p, _ = page
    qapp.clipboard().clear()
    # The offscreen platform does not deliver mouse input to this button
    # reliably, so the handler is triggered from script. A plain
    # QWebEnginePage rejects this with "NotAllowedError: ... Document is not
    # focused" (the bug the shell fixed).
    p.runJavaScript("document.getElementById('copy').click()")
    assert wait_for(qapp, lambda: p.title() == "ok" or p.title().startswith("NotAllowed")), (
        p.title()
    )
    assert p.title() == "ok", p.title()
    assert wait_for(qapp, lambda: qapp.clipboard().text() == COPIED)
