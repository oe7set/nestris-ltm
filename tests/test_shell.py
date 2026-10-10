"""Desktop shell: autostart registry entry, single instance, full app lifecycle."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QElapsedTimer

from nestris_ltm.shell import autostart
from nestris_ltm.shell.single_instance import (
    InstanceServer,
    send_to_running,
    server_name,
)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QCoreApplication]:
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def test_launch_command_starts_minimized() -> None:
    cmd = autostart.launch_command(Path("C:/cfg/config.toml"))
    assert "--minimized" in cmd
    assert "nestris_ltm" in cmd or cmd.lower().endswith(".exe --minimized")
    assert "config.toml" in cmd


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_autostart_registry_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    # A private key, so the developer's real autostart entry is never touched.
    monkeypatch.setattr(autostart, "RUN_KEY", rf"Software\NestrisLTM-Test-{uuid.uuid4().hex}")
    try:
        assert not autostart.is_enabled()
        autostart.set_enabled(True)
        assert autostart.is_enabled()
        autostart.set_enabled(False)
        assert not autostart.is_enabled()
        autostart.set_enabled(False)  # idempotent
    finally:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY)


def _send_from_other_process(command: str, name: str) -> subprocess.Popen[bytes]:
    code = (
        "import sys; from nestris_ltm.shell.single_instance import send_to_running; "
        f"sys.exit(0 if send_to_running({command!r}, {name!r}, 3000) else 1)"
    )
    return subprocess.Popen([sys.executable, "-c", code])


def test_single_instance_delivers_commands(qapp: QCoreApplication) -> None:
    name = f"nltm-test-{uuid.uuid4().hex[:8]}"
    assert not send_to_running("show", name, timeout_ms=200)  # nobody listening

    server = InstanceServer(name)
    received: list[str] = []
    server.command_received.connect(received.append)
    assert server.listen()
    try:
        # Like a real second start: another process, while our event loop runs.
        clients = [_send_from_other_process(c, name) for c in ("bogus", "show")]
        timer = QElapsedTimer()
        timer.start()
        while (not received or any(c.poll() is None for c in clients)) and timer.elapsed() < 15000:
            qapp.processEvents()
            time.sleep(0.01)
        assert [c.wait(5) for c in clients] == [0, 0]
        assert received == ["show"]  # unknown commands are ignored
    finally:
        server.close()


def test_server_name_is_per_port() -> None:
    assert server_name(7990) != server_name(7991)


def test_shell_starts_serves_and_quits(tmp_path: Path, qapp: QCoreApplication) -> None:
    """Start the real app headless-Qt, wait for HTTP, quit it via a 2nd instance."""
    port = 17000 + int(uuid.uuid4().int % 2000)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NESTRIS_LTM__")} | {
        "QT_QPA_PLATFORM": "offscreen",
        "NESTRIS_LTM__HTTP__PORT": str(port),
        "NESTRIS_LTM__MQTT__ENABLED": "false",
        "NESTRIS_LTM__DATABASE__PORT": "1",  # unreachable: the app must still start
        "NESTRIS_LTM__DATA_DIR": str(tmp_path),
        "NESTRIS_LTM__LOG__TO_FILE": "false",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "nestris_ltm", "--config", str(tmp_path / "none.toml"),
         "--minimized"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )  # fmt: skip
    # Read the output while the app runs: Qt WebEngine logs a lot when rendering
    # offscreen, and a full pipe would block the app.
    chunks: list[bytes] = []
    stdout = proc.stdout
    assert stdout is not None
    reader = threading.Thread(target=lambda: chunks.extend(iter(stdout.readline, b"")))
    reader.start()
    try:
        deadline = time.monotonic() + 30
        status = None
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                status = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).json()
                break
            except httpx.HTTPError:
                time.sleep(0.3)
        assert status is not None, "HTTP server did not come up"
        assert status["status"] == "degraded"  # no database, but serving
        assert httpx.get(f"http://127.0.0.1:{port}/", timeout=2).status_code == 200
        # Let the tray's status refresh (every 2 s) run with the database down.
        time.sleep(4.5)

        assert send_to_running("quit", server_name(port), timeout_ms=2000)
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
        reader.join(timeout=10)
        output = b"".join(chunks).decode("utf-8", "replace")
        print(output[-3000:])
    # A failing Qt slot only prints its traceback; the app keeps running.
    assert "Traceback" not in output
