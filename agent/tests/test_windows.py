import subprocess
import sys
from unittest.mock import MagicMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows platform tests", allow_module_level=True)

from gaddhub_agent import windows


def test_autostart_register_and_remove(monkeypatch):
    registry = MagicMock()
    monkeypatch.setattr(windows, "winreg", registry)
    windows.set_autostart(True)
    registry.SetValueEx.assert_called_once()
    command = registry.SetValueEx.call_args.args[-1]
    assert "pythonw.exe" in command and "--background" in command
    windows.set_autostart(False)
    registry.DeleteValue.assert_called_once()


def test_packaged_startup_command(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\GaddHub\GaddHub.exe")
    assert windows.startup_command() == '"C:\\Program Files\\GaddHub\\GaddHub.exe" --background'


def test_single_instance_lock(tmp_path):
    path = tmp_path / "agent.lock"
    first = windows.lock_instance(path)
    try:
        with pytest.raises(OSError):
            windows.lock_instance(path)
    finally:
        first.close()
    windows.lock_instance(path).close()


def test_installer_mutex_name_matches_setup_script():
    from pathlib import Path

    script = Path(__file__).parents[1] / "installer" / "GaddHub.iss"
    assert f"AppMutex={windows.INSTALLER_MUTEX}\n" in script.read_text()


def test_running_agent_exposes_installer_mutex(tmp_path):
    lock = windows.lock_instance(tmp_path / "agent.lock")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import ctypes; from ctypes import wintypes; "
                    "k=ctypes.WinDLL('kernel32', use_last_error=True); "
                    "k.OpenMutexW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]; "
                    "k.OpenMutexW.restype=wintypes.HANDLE; "
                    f"h=k.OpenMutexW(0x100000,False,{windows.INSTALLER_MUTEX!r}); "
                    "assert h, 'Installer mutex not found'; "
                    "k.CloseHandle.argtypes=[wintypes.HANDLE]; k.CloseHandle(h)"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    finally:
        lock.close()


def test_installer_mutex_creation_failure_releases_file_lock(tmp_path, monkeypatch):
    kernel32 = MagicMock()
    kernel32.CreateMutexW.return_value = None
    with monkeypatch.context() as patch:
        patch.setattr(windows, "_installer_mutex_handle", None)
        patch.setattr(windows.ctypes, "WinDLL", lambda *args, **kwargs: kernel32)
        with pytest.raises(OSError):
            windows.lock_instance(tmp_path / "agent.lock")
    windows.lock_instance(tmp_path / "agent.lock").close()
