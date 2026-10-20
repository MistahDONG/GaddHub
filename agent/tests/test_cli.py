import os
import subprocess
import sys
from pathlib import Path


def test_export_validation_without_display_or_windows_imports():
    fixture = Path(__file__).parent / "fixtures" / "synthetic-savedvariables.lua"
    environment = os.environ.copy()
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    result = subprocess.run(
        [sys.executable, "-m", "gaddhub_agent", "--check-export", str(fixture)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Valid export: 1 snapshot(s)" in result.stdout
