"""Checks of the desktop app's embedded browser, run in a separate process by
``test_shell_window.py`` (QtWebEngine must not share a process with the
other Qt tests). Prints one JSON object with the results.

Uses the real ``MainWindow`` (not just its page class), so the checks cover
what the app actually shows:

- the window's view really uses the app's page (a garbage-collected page
  once made the view fall back to a default page, silently dropping all of
  the following);
- every request to the local server carries the shell token (automatic
  admin login in the desktop app);
- a ``target="_blank"`` link and a link to another site are handed to the
  system browser (real mouse clicks = a user gesture, as in the app);
- ``navigator.clipboard.writeText`` succeeds; a plain QWebEnginePage (the
  state before the fix) does not;
- a blob download (how the admin UI exports files) asks for a path and is
  written there (QtWebEngine drops downloads nobody accepts).

Offscreen platform: the clipboard is an isolated in-process one, never the
user's real clipboard.
"""

from __future__ import annotations

import gc
import json
import os
import tempfile
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from nestris_ltm.shell.window import SHELL_TOKEN_HEADER, MainWindow

TOKEN = "test-shell-token"
COPIED = "http://127.0.0.1:7990/o/main"
PAGE = f"""<!doctype html><html><body style="margin:0">
<a id="view" href="/view/highscore" target="_blank" rel="noopener"
   style="position:absolute;left:0;top:0;width:100px;height:40px;display:block">open</a>
<a id="ext" href="https://retroverse.at/"
   style="position:absolute;left:0;top:50px;width:100px;height:40px;display:block">site</a>
<button id="copy" onclick="navigator.clipboard.writeText('{COPIED}')
  .then(() => document.title = 'ok', e => document.title = 'err:' + e)">copy</button>
<button id="dl" onclick="const u = window.URL.createObjectURL(new Blob([JSON.stringify({{x: 1}})], {{type: 'application/json'}}));
  const a = document.createElement('a'); a.href = u; a.download = 'export.nltm-scenes.json';
  document.body.append(a); a.click(); a.remove();">download</button>
</body></html>""".encode()

seen_tokens: list[str | None] = []


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        seen_tokens.append(self.headers.get(SHELL_TOKEN_HEADER.decode()))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    origin = QUrl(f"http://127.0.0.1:{httpd.server_address[1]}/")
    app = QApplication([])

    def wait_for(check: Callable[[], object], ms: int = 10_000) -> bool:
        timer = QElapsedTimer()
        timer.start()
        while timer.elapsed() < ms:
            app.processEvents()
            if check():
                return True
        return False

    def focus(view: QWebEngineView) -> None:
        # In the app the click on the copy button focuses the document.
        view.activateWindow()
        (view.focusProxy() or view).setFocus()
        wait_for(lambda: False, 300)

    def copy(page: QWebEnginePage, view: QWebEngineView) -> str:
        # The offscreen platform does not deliver mouse input to the button
        # reliably; the handler is triggered from script.
        focus(view)
        page.runJavaScript("document.getElementById('copy').click()")
        wait_for(lambda: page.title() == "ok" or page.title().startswith("err"))
        return page.title()

    def click(view: QWebEngineView, x: int, y: int) -> None:
        target = view.focusProxy() or view
        QTest.mouseClick(
            target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y)
        )

    out: dict[str, object] = {"origin": origin.toString()}

    # A plain page first: the state before the fix.
    plain_profile = QWebEngineProfile()
    plain = QWebEnginePage(plain_profile)
    plain_view = QWebEngineView()
    plain_view.setPage(plain)
    plain_view.resize(400, 300)
    plain_view.show()
    loaded: list[bool] = []
    plain.loadFinished.connect(loaded.append)
    plain.setUrl(origin)
    wait_for(lambda: loaded)
    out["plain_copy_result"] = copy(plain, plain_view)
    plain_view.hide()
    seen_tokens.clear()

    # The real window.
    window = MainWindow(origin.toString().rstrip("/"), TOKEN)
    opened: list[str] = []
    window._page._opener = lambda url: opened.append(url.toString())
    window.resize(800, 500)
    window.show()
    gc.collect()  # a page without a live reference would be gone now
    view = window._view
    out["view_uses_app_page"] = view.page() is window._page
    loaded.clear()
    view.page().loadFinished.connect(loaded.append)
    window.load_app("/")
    wait_for(lambda: loaded)
    out["tokens_seen"] = list(seen_tokens)
    out["opened_on_load"] = list(opened)

    app.clipboard().clear()
    out["copy_result"] = copy(view.page(), view)
    wait_for(lambda: app.clipboard().text() == COPIED, 3000)
    out["clipboard"] = app.clipboard().text()

    click(view, 20, 20)  # target="_blank" to the app's own host
    wait_for(lambda: opened)
    click(view, 20, 70)  # plain link to another site
    wait_for(lambda: len(opened) >= 2)
    out["opened"] = list(opened)

    # Download: the window asks for a path (stubbed) and writes the file.
    target = os.path.join(tempfile.mkdtemp(), "saved.json")
    asked: list[str] = []
    window.ask_save_path = lambda suggested: (asked.append(suggested), target)[1]
    view.page().runJavaScript("document.getElementById('dl').click()")
    wait_for(lambda: os.path.exists(target) and os.path.getsize(target) > 0)
    out["download_asked"] = [os.path.basename(a) for a in asked]
    saved = Path(target)
    out["download_content"] = saved.read_text(encoding="utf-8") if saved.exists() else None

    print("RESULT " + json.dumps(out), flush=True)
    httpd.shutdown()
    # Skip Qt/Chromium teardown: the result is out, the process just ends.
    os._exit(0)


if __name__ == "__main__":
    main()
