"""The embedded admin browser: new windows open in the system browser, the
page may write to the clipboard.

The checks run in a separate process (``qt_browser_check.py``): QtWebEngine
crashes intermittently when it shares a process with the other Qt tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets")

SCRIPT = Path(__file__).with_name("qt_browser_check.py")


@pytest.fixture(scope="module")
def result() -> dict[str, object]:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=Path(__file__).parent.parent,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert lines, (
        f"browser check failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr[-2000:]}"
    )
    data: dict[str, object] = json.loads(lines[-1].removeprefix("RESULT "))
    return data


def test_new_window_links_open_in_the_system_browser(result: dict[str, object]) -> None:
    origin = str(result["origin"])
    assert result["opened_on_load"] == []  # the app's own page stays in the app
    assert result["opened"] == [origin + "view/highscore", "https://retroverse.at/"]


def test_page_may_write_the_clipboard(result: dict[str, object]) -> None:
    assert result["copy_result"] == "ok"
    assert result["clipboard"] == "http://127.0.0.1:7990/o/main"
    # Without the shell's settings QtWebEngine refuses (NotAllowedError) or
    # leaves the permission request unanswered: copying silently fails (the bug).
    assert result["plain_copy_result"] != "ok"
