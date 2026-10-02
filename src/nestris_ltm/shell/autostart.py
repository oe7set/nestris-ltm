"""Start with Windows: the per-user ``Run`` registry key.

The entry starts NestrisLTM minimized to the tray. In a PyInstaller build
the executable itself is registered; in development ``pythonw -m
nestris_ltm`` is used so no console window appears.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "NestrisLTM"


def is_supported() -> bool:
    return sys.platform == "win32"


def launch_command(config: Path | None = None) -> str:
    if getattr(sys, "frozen", False):
        args = [sys.executable]
    else:
        python = Path(sys.executable)
        pythonw = python.with_name("pythonw.exe")
        args = [str(pythonw if pythonw.exists() else python), "-m", "nestris_ltm"]
    args.append("--minimized")
    if config is not None:
        args += ["--config", str(config)]
    return subprocess.list2cmdline(args)


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    return True


def set_enabled(enabled: bool, config: Path | None = None) -> None:
    if not is_supported():
        raise RuntimeError("autostart is only supported on Windows")
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command(config))
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, VALUE_NAME)
