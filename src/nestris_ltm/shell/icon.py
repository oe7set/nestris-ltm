"""The application icon, drawn at runtime (no binary assets needed).

A T tetromino in Retroverse colors; the tray variant carries a status dot.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

_BLOCK = QColor("#f5b800")  # gold, as in the highscore kiosk
_EDGE = QColor("#7a5c00")
_BG = QColor("#111827")


class Health(Enum):
    OK = "#22c55e"
    DEGRADED = "#f59e0b"
    DOWN = "#ef4444"
    STARTING = "#94a3b8"


def _draw(size: int, health: Health | None) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_BG)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.18, size * 0.18)

    cell = size / 4.2
    ox = (size - 3 * cell) / 2
    oy = size * 0.24
    for cx, cy in ((0, 0), (1, 0), (2, 0), (1, 1)):
        rect = QRectF(ox + cx * cell, oy + cy * cell, cell, cell).adjusted(1, 1, -1, -1)
        p.setBrush(_BLOCK)
        p.setPen(_EDGE)
        p.drawRect(rect)

    if health is not None:
        r = size * 0.36
        dot = QRectF(size - r - 1, size - r - 1, r, r)
        p.setPen(QColor("#000000"))
        p.setBrush(QColor(health.value))
        p.drawEllipse(dot)
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(size, None))
    return icon


def tray_icon(health: Health) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48):
        icon.addPixmap(_draw(size, health))
    return icon
