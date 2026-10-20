import ctypes
import msvcrt
import os
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "GaddHubAgent"
INSTALLER_MUTEX = r"Local\GaddHub.Agent.Running"
_installer_mutex_handle: int | None = None


def hold_installer_mutex() -> None:
    global _installer_mutex_handle
    if _installer_mutex_handle is not None:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    handle = create_mutex(None, False, INSTALLER_MUTEX)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    # Inno Setup checks this mutex; Windows closes it when the process exits.
    _installer_mutex_handle = handle


def data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("Windows LOCALAPPDATA is unavailable.")
    directory = Path(base) / "GaddHub"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--background"]
    else:
        executable = Path(sys.executable).with_name("pythonw.exe")
        if not executable.is_file():
            raise OSError("pythonw.exe not found; reinstall Python with tkinter support.")
        args = [str(executable), "-m", "gaddhub_agent", "--background"]
    return subprocess.list2cmdline(args)


def set_autostart(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass  # Already disabled.


def lock_instance(path: Path) -> BinaryIO:
    file = path.open("a+b")
    if path.stat().st_size == 0:
        file.write(b"0")
        file.flush()
    file.seek(0)
    try:
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        hold_installer_mutex()
    except OSError:
        file.close()
        raise
    return file
