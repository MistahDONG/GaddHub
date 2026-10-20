import json

import pytest
from gaddhub_agent.export import (
    MAX_FILE_BYTES,
    ExportError,
    LuaReader,
    canonical_snapshot,
    read_export,
)


def test_valid_export_and_stable_hash(export_data):
    first = read_export(export_data)
    second = read_export(export_data.replace(b'["schema_version"] = 1,', b"schema_version=1,"))
    assert first == second
    assert len(first) == 1
    content_hash, payload = first[0]
    assert len(content_hash) == 64
    snapshot = json.loads(payload)
    assert snapshot["character"]["name"] == "Example"
    assert snapshot["sections"]["equipment"]["items"][0]["slot_id"] == 1
    assert "items" not in snapshot["sections"]["bank"]


@pytest.mark.parametrize(
    "data",
    [
        b"GuildSyncDB = {",
        b"GuildSyncDB = os.execute('anything')",
        b"GuildSyncDB = {}; os.execute('anything')",
        b"OtherDB = {}",
        b"GuildSyncDB = { schema_version=1, schema_version=2, snapshots={} }",
        b"GuildSyncDB = { schema_version=99, snapshots={} }",
        b"GuildSyncDB = { schema_version=true, snapshots={} }",
        b"GuildSyncDB = { schema_version=1, snapshots={ [3]={} } }",
        b"\xff",
    ],
)
def test_invalid_exports_are_rejected(data):
    with pytest.raises(ExportError):
        read_export(data)


def test_file_and_depth_limits():
    with pytest.raises(ExportError, match="8 MiB"):
        read_export(b" " * (MAX_FILE_BYTES + 1))
    with pytest.raises(ExportError, match="complexity"):
        LuaReader("GuildSyncDB = " + "{" * 40 + "}" * 40).read()


def test_no_partial_batch(export_data):
    data = export_data.replace(b'["schema_version"] = 1,', b'["schema_version"] = 99,')
    with pytest.raises(ExportError):
        read_export(data)


def test_lua_array_comments_and_utf8():
    value = LuaReader(
        'GuildSyncDB = { -- comment\n ["a"] = { [1] = "G\\195\\164dda", [2]="x\\n" } }'
    ).read()
    assert value == {"a": ["G\u00e4dda", "x\n"]}


def test_unknown_section_cannot_masquerade_as_empty(export_data):
    data = export_data.replace(
        b'["bank"] = { ["status"] = "unavailable", }',
        b'["bank"] = { ["status"] = "unavailable", ["items"] = {}, }',
    )
    with pytest.raises(ExportError, match="schema"):
        read_export(data)


def test_available_empty_list_is_allowed(export_data):
    data = export_data.replace(
        b'["bank"] = { ["status"] = "unavailable", }',
        b'["bank"] = { ["status"] = "available", ["items"] = {}, }',
    )
    assert json.loads(read_export(data)[0][1])["sections"]["bank"]["items"] == []


def test_timestamp_must_be_utc(export_data):
    with pytest.raises(ExportError, match="captured_at"):
        read_export(export_data.replace(b"2026-10-20T12:00:00Z", b"not-a-date"))


def test_snapshot_size_limit(export_data):
    snapshot = json.loads(read_export(export_data)[0][1])
    snapshot["sections"]["equipment"]["items"] = [{"data": "x" * (2 * 1024 * 1024)}]
    with pytest.raises(ExportError, match="2 MiB"):
        canonical_snapshot(snapshot)
