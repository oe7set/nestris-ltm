"""Single-instance guard over a local socket (named pipe on Windows).

The first instance listens; a second instance connects, sends a command
(``show`` or ``quit``) and exits. A stale socket left by a crash is removed.
"""

from __future__ import annotations

import getpass
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

COMMANDS = ("show", "quit")


def server_name(port: int, app_id: str = "NestrisLTM") -> str:
    """Per user and HTTP port: two instances on one port could never both run,
    while a second configuration on another port may."""
    user = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser())
    return f"{app_id}-{user}-{port}"


def send_to_running(command: str, name: str, timeout_ms: int = 500) -> bool:
    """Deliver ``command`` to a running instance. Returns False if none runs."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(command.encode("ascii") + b"\n")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Listens for commands from later instances."""

    command_received = Signal(str)

    def __init__(self, name: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        if self._server.listen(self.name):
            return True
        # A crashed instance can leave the name behind (on Unix the socket file).
        QLocalServer.removeServer(self.name)
        return self._server.listen(self.name)

    def close(self) -> None:
        self._server.close()

    def _on_connection(self) -> None:
        while (socket := self._server.nextPendingConnection()) is not None:
            socket.readyRead.connect(lambda s=socket: self._read(s))
            # Read what is left before the socket goes away.
            socket.disconnected.connect(lambda s=socket: (self._read(s), s.deleteLater()))
            # A fast client may have written (and even closed) before we got
            # here; that data never triggers readyRead again.
            self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        while socket.canReadLine():
            command = bytes(socket.readLine().data()).decode("ascii", "replace").strip()
            if command in COMMANDS:
                self.command_received.emit(command)
