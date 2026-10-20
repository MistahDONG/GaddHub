import ctypes
import os
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

import pytest

if sys.platform != "win32":
    pytest.skip("Windows installer integration tests", allow_module_level=True)

import winreg

from gaddhub_agent.windows import INSTALLER_MUTEX

pytestmark = pytest.mark.skipif(
    not os.environ.get("GADDHUB_INSTALLER"), reason="Requires a built Windows installer"
)
PRODUCT_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{68CB44D8-14A0-480F-8475-324BF8335695}_is1"
)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def registry_value(key: str, name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            return winreg.QueryValueEx(handle, name)[0]
    except FileNotFoundError:
        return None


def set_run_command(command: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as handle:
        winreg.SetValueEx(handle, "GaddHubAgent", 0, winreg.REG_SZ, command)


def run_program(executable: Path, *args: str) -> int:
    result = subprocess.run([str(executable), *args], timeout=90, capture_output=True, check=False)
    return result.returncode


def uninstall(destination: Path, *args: str) -> None:
    uninstaller = destination / "unins000.exe"
    log_file = destination.parent / f"uninstall-{uuid.uuid4()}.log"
    assert (
        run_program(
            uninstaller,
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/NOCANCEL",
            *args,
            f"/LOG={log_file}",
        )
        == 0
    )
    # Inno's launcher exits before the temporary uninstaller's post-uninstall callback.
    deadline = time.monotonic() + 15
    finished = False
    while time.monotonic() < deadline:
        if log_file.exists() and "Log closed." in log_file.read_text(encoding="utf-8-sig"):
            finished = True
            break
        time.sleep(0.05)
    assert finished, "Uninstaller did not finish its post-uninstall cleanup."
    assert not uninstaller.exists()
    assert registry_value(PRODUCT_KEY, "UninstallString") is None


@pytest.fixture
def installation(tmp_path):
    if registry_value(PRODUCT_KEY, "UninstallString") is not None:
        pytest.skip("Existing installed GaddHub detected; refusing to modify it.")
    if registry_value(RUN_KEY, "GaddHubAgent") is not None:
        pytest.skip("Existing autostart detected; refusing to modify it.")
    shortcut = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "GaddHub"
        / "GaddHub.lnk"
    )
    if shortcut.exists():
        pytest.skip("Existing GaddHub shortcut detected; refusing to modify it.")
    installer = Path(os.environ["GADDHUB_INSTALLER"]).resolve()
    assert installer.is_file()
    destination = tmp_path / "GaddHub installed"
    group = "GaddHub"
    arguments = (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        f"/DIR={destination}",
    )
    try:
        yield installer, destination, group, arguments
    finally:
        try:
            location = registry_value(PRODUCT_KEY, "InstallLocation")
            if location is not None and Path(location) == destination:
                uninstall(destination)
        finally:
            # Only remove entries created here, never another installation's.
            command = registry_value(RUN_KEY, "GaddHubAgent")
            if command in (
                f'"{destination / "GaddHub.exe"}" --background',
                '"C:\\GaddHub-Installer-Test\\GaddHub.exe" --background',
            ):
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as handle:
                    winreg.DeleteValue(handle, "GaddHubAgent")


def test_install_upgrade_and_uninstall(installation, tmp_path):
    installer, destination, group, arguments = installation
    data_directory = Path(os.environ["LOCALAPPDATA"]) / "GaddHub"
    existed = data_directory.exists()
    data_directory.mkdir(exist_ok=True)
    marker = data_directory / f"installer-test-{uuid.uuid4()}.txt"
    marker.write_text("Synthetic installer retention test", encoding="utf-8")
    try:
        assert run_program(installer, *arguments, f"/LOG={tmp_path / 'install.log'}") == 0
        executable = destination / "GaddHub.exe"
        assert executable.is_file()
        assert (destination / "_internal").is_dir()
        shortcut = (
            Path(os.environ["APPDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / group
            / "GaddHub.lnk"
        )
        assert shortcut.is_file()
        location = registry_value(PRODUCT_KEY, "InstallLocation")
        assert location is not None and Path(location) == destination
        assert registry_value(RUN_KEY, "GaddHubAgent") is None
        fixture = Path(__file__).parent / "fixtures" / "synthetic-savedvariables.lua"
        assert run_program(executable, "--check-export", str(fixture)) == 0
        assert run_program(executable, "--check-export", str(tmp_path / "missing.lua")) == 1
        # An existing portable autostart follows the installed path on upgrade.
        set_run_command('"C:\\GaddHub-Installer-Test\\GaddHub.exe" --background')
        assert run_program(installer, *arguments, f"/LOG={tmp_path / 'upgrade.log'}") == 0
        assert registry_value(RUN_KEY, "GaddHubAgent") == f'"{executable}" --background'
        assert marker.read_text(encoding="utf-8") == "Synthetic installer retention test"
        uninstall(destination, f"/LOG={tmp_path / 'uninstall.log'}")
        assert not executable.exists()
        assert not shortcut.exists()
        assert registry_value(PRODUCT_KEY, "UninstallString") is None
        assert registry_value(RUN_KEY, "GaddHubAgent") is None
        assert marker.exists(), "Uninstall must preserve local user data."
    finally:
        marker.unlink(missing_ok=True)
        if not existed and not any(data_directory.iterdir()):
            data_directory.rmdir()


def test_uninstall_keeps_autostart_for_another_location(installation):
    installer, destination, _, arguments = installation
    assert run_program(installer, *arguments) == 0
    foreign = '"C:\\GaddHub-Installer-Test\\GaddHub.exe" --background'
    set_run_command(foreign)
    uninstall(destination)
    assert registry_value(RUN_KEY, "GaddHubAgent") == foreign


def test_installer_refuses_running_agent(installation, tmp_path):
    installer, destination, _, arguments = installation
    assert run_program(installer, *arguments) == 0
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "isolated-user-data")
    agent = subprocess.Popen(
        [str(destination / "GaddHub.exe"), "--background"],
        env=environment,
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        deadline = time.monotonic() + 10
        ready = False
        while agent.poll() is None and time.monotonic() < deadline:
            handle = kernel32.OpenMutexW(0x100000, False, INSTALLER_MUTEX)
            if handle:
                kernel32.CloseHandle(handle)
                ready = True
                break
            time.sleep(0.05)
        assert ready, "Installed agent did not start and expose its installer mutex."
        assert run_program(installer, *arguments, f"/LOG={tmp_path / 'busy.log'}") != 0
        assert (
            run_program(
                destination / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
            )
            != 0
        )
        assert (destination / "GaddHub.exe").exists()
        assert agent.poll() is None
    finally:
        agent.terminate()
        agent.wait(timeout=10)
