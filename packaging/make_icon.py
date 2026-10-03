"""Writes packaging/icon.ico from the runtime app icon (shell/icon.py); the .ico is committed."""

from pathlib import Path

from PySide6.QtGui import QGuiApplication

from nestris_ltm.shell.icon import _draw

app = QGuiApplication([])
out = Path(__file__).with_name("icon.ico")
assert _draw(256, None).toImage().save(str(out), "ICO"), "Qt ICO writer missing"
print(out)
