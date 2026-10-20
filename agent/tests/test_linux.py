import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from gaddhub_agent import linux


def test_linux_data_directory_uses_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert linux.data_directory() == tmp_path / "GaddHub"
    assert linux.data_directory().is_dir()


@pytest.mark.parametrize("value", ["", "relative-path"])
def test_relative_or_missing_xdg_uses_home(tmp_path, monkeypatch, value):
    monkeypatch.setenv("XDG_DATA_HOME", value)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert linux.data_directory() == tmp_path / ".local" / "share" / "GaddHub"


def test_linux_autostart_and_application_launcher(tmp_path, monkeypatch):
    data = tmp_path / "data"
    config = tmp_path / "config"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setattr(
        linux, "sys", SimpleNamespace(executable="python with spaces", frozen=False)
    )
    linux.set_autostart(True)
    startup = config / "autostart" / "gaddhub-agent.desktop"
    launcher = data / "applications" / "gaddhub-agent.desktop"
    startup_text = startup.read_text()
    assert 'Exec="python with spaces" "-m" "gaddhub_agent" "--background"\n' in startup_text
    assert "--background" not in launcher.read_text()
    linux.set_autostart(False)
    assert not startup.exists()
    assert launcher.exists()
    linux.set_autostart(False)


def test_packaged_linux_launcher(monkeypatch):
    monkeypatch.setattr(
        linux, "sys", SimpleNamespace(executable="/opt/Gadd Hub/GaddHub", frozen=True)
    )
    assert 'Exec="/opt/Gadd Hub/GaddHub" "--background"\n' in linux.desktop_entry(True)
    assert '"-m"' not in linux.desktop_entry(False)


def test_desktop_exec_escaping():
    assert linux.desktop_argument("has space%") == '"has space%%"'
    for character in ('"', "\\", "$", "`"):
        escaped = linux.desktop_argument(character)
        # Both Desktop Entry string escaping and Exec quoting must be preserved.
        assert "\\\\" in escaped
    with pytest.raises(ValueError, match="control"):
        linux.desktop_argument("bad\nentry")


def test_autostart_write_failure_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    blocker = tmp_path / "applications"
    blocker.write_text("not a directory")
    with pytest.raises(OSError):
        linux.set_autostart(True)


@pytest.mark.skipif(sys.platform != "linux", reason="Requires Linux flock")
def test_native_linux_single_instance_lock(tmp_path):
    path = tmp_path / "agent.lock"
    first = linux.lock_instance(path)
    try:
        with pytest.raises(OSError):
            linux.lock_instance(path)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; from gaddhub_agent.linux import lock_instance; "
                    "import sys; lock_instance(Path(sys.argv[1]))"
                ),
                str(path),
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert result.returncode != 0
    finally:
        first.close()
    linux.lock_instance(path).close()


@pytest.mark.skipif(sys.platform != "linux", reason="Requires Linux desktop-file-utils")
def test_native_desktop_entry_validation(tmp_path, monkeypatch):
    executable = shutil.which("desktop-file-validate")
    assert executable is not None, "Install desktop-file-utils for native Linux tests."
    monkeypatch.setattr(
        linux,
        "sys",
        SimpleNamespace(executable='/opt/Gadd Hub/%test/"quoted"/$var`/GaddHub', frozen=True),
    )
    path = tmp_path / "gaddhub-agent.desktop"
    linux.write_entry(path, True)
    result = subprocess.run(
        [executable, str(path)], capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_platform_routes_native_implementation():
    from gaddhub_agent import platform

    assert platform.lock_instance.__module__ == (
        "gaddhub_agent.windows" if os.name == "nt" else "gaddhub_agent.linux"
    )
