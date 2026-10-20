import os
import sys
from pathlib import Path
from typing import BinaryIO


def xdg_directory(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable, "")
    return Path(value) if value and Path(value).is_absolute() else fallback


def data_directory() -> Path:
    directory = xdg_directory("XDG_DATA_HOME", Path.home() / ".local" / "share") / "GaddHub"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def desktop_argument(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ValueError("Launcher arguments must not contain control characters.")
    escaped = value.replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        escaped = escaped.replace(char, "\\" + char)
    # Desktop-file string escaping is applied after Exec argument escaping.
    return '"' + escaped.replace("\\", "\\\\") + '"'


def desktop_entry(background: bool) -> str:
    args = [sys.executable]
    if not getattr(sys, "frozen", False):
        args += ["-m", "gaddhub_agent"]
    if background:
        args.append("--background")
    command = " ".join(desktop_argument(arg) for arg in args)
    return (
        "[Desktop Entry]\nType=Application\nName=GaddHub Agent\n"
        "Comment=Synchronize configured WoW SavedVariables snapshots\n"
        f"Exec={command}\nTerminal=false\nCategories=Game;Utility;\n"
    )


def write_entry(path: Path, background: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(desktop_entry(background), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def set_autostart(enabled: bool) -> None:
    applications = xdg_directory("XDG_DATA_HOME", Path.home() / ".local" / "share") / "applications"
    config = xdg_directory("XDG_CONFIG_HOME", Path.home() / ".config")
    autostart = config / "autostart" / "gaddhub-agent.desktop"
    write_entry(applications / "gaddhub-agent.desktop", background=False)
    if enabled:
        write_entry(autostart, background=True)
    else:
        autostart.unlink(missing_ok=True)


def lock_instance(path: Path) -> BinaryIO:
    import fcntl

    file = path.open("a+b")
    try:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        file.close()
        raise
    return file
