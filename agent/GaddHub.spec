from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
tray_backends = (
    ["pystray._win32"] if sys.platform == "win32"
    else ["pystray._appindicator", "pystray._gtk", "pystray._xorg"]
)
watcher_backend = (
    "watchdog.observers.read_directory_changes" if sys.platform == "win32"
    else "watchdog.observers.inotify"
)
analysis = Analysis(
    [str(root / "agent" / "launcher.py")],
    pathex=[str(root / "agent" / "src")],
    binaries=[],
    datas=collect_data_files("schemas"),
    hiddenimports=["schemas", *tray_backends, watcher_backend],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="GaddHub",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="GaddHub",
)
