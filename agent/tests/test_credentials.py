import json
from pathlib import Path

import pytest
from gaddhub_agent.credentials import Credentials, CredentialsError

ENDPOINT = "https://example.invalid/v1/sync/snapshots"


def test_password_file_roundtrip_and_endpoint_scope(tmp_path):
    path = tmp_path / "credentials.json"
    credentials = Credentials(path)
    assert credentials.get(ENDPOINT) == ""
    assert not path.exists()
    credentials.set(ENDPOINT, "first-password")
    credentials.set(ENDPOINT + "/other", "other-password")
    credentials.set(ENDPOINT, "updated-password")
    assert Credentials(path).get(ENDPOINT) == "updated-password"
    assert Credentials(path).get(ENDPOINT + "/other") == "other-password"
    assert Credentials(path).get("https://elsewhere.invalid/") == ""
    assert json.loads(path.read_text(encoding="utf-8"))[ENDPOINT] == "updated-password"
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize("password", ["", "bad\nheader", "has space", "\u00e4"])
def test_invalid_password_does_not_change_file(tmp_path, password):
    path = tmp_path / "credentials.json"
    credentials = Credentials(path)
    credentials.set(ENDPOINT, "original")
    before = path.read_bytes()
    with pytest.raises(CredentialsError):
        credentials.set(ENDPOINT, password)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "content",
    [
        b'{"https://example.invalid": "private-value',
        b"[]",
        b"null",
        b'{"endpoint": 123}',
        b'{"endpoint": ""}',
        b'{"endpoint": "bad\\nprivate-value"}',
        b"\xff",
    ],
)
def test_corrupt_file_is_reported_without_leaking_or_overwriting(tmp_path, content):
    path = tmp_path / "credentials.json"
    path.write_bytes(content)
    credentials = Credentials(path)
    for operation in (
        lambda: credentials.get(ENDPOINT),
        lambda: credentials.set(ENDPOINT, "new-password"),
    ):
        with pytest.raises(CredentialsError) as error:
            operation()
        assert "private-value" not in str(error.value)
        assert path.read_bytes() == content


def test_failed_replace_preserves_existing_password_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    credentials = Credentials(path)
    credentials.set(ENDPOINT, "original")

    def denied(self, target):
        raise PermissionError("Test replacement failure")

    monkeypatch.setattr(Path, "replace", denied)
    with pytest.raises(PermissionError):
        credentials.set(ENDPOINT, "new-password")
    assert credentials.get(ENDPOINT) == "original"
    assert not path.with_suffix(".tmp").exists()


def test_file_access_error_is_not_treated_as_missing_password(tmp_path, monkeypatch):
    def denied(self, **kwargs):
        raise PermissionError("Test read failure")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError):
        Credentials(tmp_path / "credentials.json").get(ENDPOINT)
