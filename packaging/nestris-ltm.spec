# PyInstaller spec: one folder, two executables sharing the same files.
#
#   NestrisLTM.exe   tray app with the admin window (no console); autostart target
#   nestris-ltm.exe  console CLI: configure, check, autostart, migrate,
#                    set-admin-password, simulate, --headless
#
# Build with packaging/build.ps1 (it builds the admin UI and overlays first).
# ruff: noqa

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "nestris_ltm"
for built in ("web/admin/index.html", "web/overlay/index.html"):
    if not (PKG / built).is_file():
        raise SystemExit(f"{built} missing: run 'pnpm build' in frontend/ (or packaging/build.ps1)")


def tree(rel):
    """Ship a package directory as plain files (read via importlib.resources)."""
    return (str(PKG / rel), f"nestris_ltm/{rel}")


# Dev tools in the venv that the analysis would otherwise drag in (pydantic
# ships a mypy plugin).
DEV_TOOLS = ["mypy", "mypyc", "librt", "ast_serialize", "pytest", "_pytest", "ruff", "pyinstaller"]

a = Analysis(
    [str(PKG / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        tree("web"),
        tree("kiosk"),
        tree("api/pages"),
        # Alembic loads env.py and the revisions from the file system.
        tree("db/migrations"),
    ],
    hiddenimports=(
        collect_submodules("uvicorn")  # loop/protocol implementations chosen by name
        + collect_submodules("alembic")
        + collect_submodules("sqlalchemy.dialects.postgresql")
        + ["asyncpg", "aiomqtt", "nestris_ltm.db.models", "nestris_ltm.shell.app"]
    ),
    excludes=["tkinter", *DEV_TOOLS],
    noarchive=False,
)

# PySide6 hooks collect far more of Qt than a QWebEngineView + tray needs.
DROP = ("Qt63D", "Qt6Quick3D", "Qt6Charts", "Qt6Graphs", "Qt6DataVisualization",
        "Qt6QuickControls2", "Qt6QuickDialogs2", "Qt6QuickTemplates2", "Qt6ShaderTools",
        "Qt6Multimedia", "Qt6SpatialAudio", "Qt6Pdf", "Qt6VirtualKeyboard", "Qt6Sensors",
        "Qt6Bluetooth", "Qt6Nfc", "Qt6SerialBus", "Qt6SerialPort", "Qt6Scxml",
        "Qt6StateMachine", "Qt6RemoteObjects", "Qt6Designer", "Qt6Help", "Qt6Sql", "Qt6Test",
        "Qt6TextToSpeech", "Qt6Location", "Qt6HttpServer", "Qt6WebSockets", "Qt6Xml")
KEEP_LOCALES = ("de.pak", "en-US.pak", "en-GB.pak")


def keep(entry):
    dest = entry[0].replace("\\", "/")
    name = dest.rsplit("/", 1)[-1]
    if "PySide6/qml/" in dest or "__pycache__" in dest:
        return False
    if name.startswith(DROP):
        return False
    if "qtwebengine_locales/" in dest and not name.endswith(KEEP_LOCALES):
        return False
    if "PySide6/translations/" in dest and name.endswith(".qm") and not ("_de" in name or "_en" in name):
        return False
    return True


a.binaries = [e for e in a.binaries if keep(e)]
a.datas = [e for e in a.datas if keep(e)]
pyz = PYZ(a.pure)

icon = str(ROOT / "packaging" / "icon.ico")
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NestrisLTM", console=False, icon=icon)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="nestris-ltm", console=True, icon=icon)
COLLECT(gui, cli, a.binaries, a.datas, name="NestrisLTM")
