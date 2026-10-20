from pathlib import Path

import pytest


@pytest.fixture
def export_data() -> bytes:
    return (Path(__file__).parent / "fixtures" / "synthetic-savedvariables.lua").read_bytes()
