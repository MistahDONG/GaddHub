import json
import logging
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from gaddhub_agent.config import DEFAULT_SERVER_URL, Settings, validate_url
from gaddhub_agent.export import read_export
from gaddhub_agent.store import Store
from gaddhub_agent.sync import Engine, UploadResult, retry_after

URL = "https://example.invalid/v1/sync/snapshots"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/upload",
        "https://user:pass@example.com/upload",
        "https://example.com/?password=secret",
        "https://example.com/#secret",
        "https://example.com:0",
        "https://example.com:bad",
        "https:///missing",
        "https://example.com\\bad",
        "https://example.com/\n",
    ],
)
def test_only_https_without_embedded_secrets(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_settings_roundtrip_has_no_password(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(server_url=URL)
    settings.save(path)
    assert Settings.load(path) == settings
    assert "password" not in path.read_text()


def test_example_endpoint_is_default_but_existing_settings_are_preserved(tmp_path):
    path = tmp_path / "settings.json"
    assert Settings.load(path).server_url == DEFAULT_SERVER_URL
    assert ".invalid/" in DEFAULT_SERVER_URL
    settings = Settings(server_url="https://existing.example.org/upload")
    settings.save(path)
    assert Settings.load(path).server_url == settings.server_url


@pytest.mark.parametrize(
    "settings",
    [
        Settings(stable_seconds=0),
        Settings(poll_seconds=float("nan")),
        Settings(rescan_seconds=float("inf")),
        Settings(**json.loads('{"autostart": "yes"}')),
        Settings(sources=["relative.lua"]),
        Settings(log_level="INVALID"),
    ],
)
def test_invalid_settings(settings):
    with pytest.raises(ValueError):
        settings.validate()


def test_persistence_dedupe_and_destination_isolation(tmp_path, export_data):
    path = tmp_path / "queue.sqlite3"
    content_hash, payload = read_export(export_data)[0]
    store = Store(path)
    store.enqueue(URL, content_hash, payload)
    store.enqueue(URL, content_hash, payload)
    assert store.status(URL)[:2] == (1, 0)
    store.close()


def test_source_filename_is_migrated_and_survives_restart(tmp_path, export_data):
    path = tmp_path / "legacy.sqlite3"
    content_hash, payload = read_export(export_data)[0]
    with sqlite3.connect(path) as database:
        database.execute("""
            CREATE TABLE uploads (
                destination TEXT NOT NULL, hash TEXT NOT NULL, payload BLOB,
                state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0, error TEXT, acknowledged_at REAL,
                PRIMARY KEY (destination, hash)
            )
        """)
        database.execute(
            "INSERT INTO uploads (destination, hash, payload) VALUES (?, ?, ?)",
            (URL, content_hash, payload),
        )
    store = Store(path)
    assert store.due(URL) == (content_hash, payload, 0)
    assert store.source_name(URL, content_hash) == ""
    assert not store.enqueue(URL, content_hash, payload, "GuildSync.lua")
    store.close()
    store = Store(path)
    assert store.source_name(URL, content_hash) == "GuildSync.lua"
    assert store.due(URL) == (content_hash, payload, 0)
    assert store.enqueue(URL + "/other", content_hash, payload, "Other.lua")
    store.close()
    store = Store(path)
    assert store.due(URL) == (content_hash, payload, 0)
    store.acknowledge(URL, content_hash)
    store.close()
    store = Store(path)
    store.enqueue(URL, content_hash, payload)
    assert store.due(URL) is None
    store.enqueue(URL + "/other", content_hash, payload)
    assert store.due(URL + "/other") is not None
    assert store.status(URL)[2] is not None
    assert store.db.execute(
        "SELECT payload FROM uploads WHERE destination=?", (URL,)
    ).fetchone() == (None,)
    store.close()


def test_retry_and_permanent_rejections(tmp_path):
    store = Store(tmp_path / "queue.sqlite3")
    store.enqueue(URL, "hash", b"{}")
    store.fail(URL, "hash", 1, 3600, "temporary", False)
    assert store.due(URL) is None
    store.retry(URL)
    assert store.due(URL) is not None
    store.fail(URL, "hash", 2, 0, "invalid schema", True)
    assert store.status(URL)[:2] == (0, 1)
    assert store.due(URL) is None
    store.retry(URL)
    assert store.due(URL) is not None
    store.close()


def make_engine(tmp_path, export_data, sender):
    source = tmp_path / "GuildSync.lua"
    source.write_bytes(export_data)
    settings = Settings(
        server_url=URL,
        sources=[str(source)],
        stable_seconds=0.2,
        poll_seconds=0.2,
        rescan_seconds=0.2,
    )
    store = Store(tmp_path / "queue.sqlite3")
    messages = []
    engine = Engine(settings, "test-password", store, messages.append, sender)
    return source, store, engine, messages


def test_stable_file_upload_and_periodic_dedupe(tmp_path, export_data, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: clock[0])
    sent = []

    def sender(url, secret, content_hash, payload):
        sent.append(json.loads(payload))
        return UploadResult(True, "OK")

    source, store, engine, messages = make_engine(tmp_path, export_data, sender)
    engine.tick()
    assert sent == []
    clock[0] += 0.3
    engine.tick()
    assert len(sent) == 1
    clock[0] += 1
    engine.tick()
    assert len(sent) == 1
    # The watcher delivers a change; file scanning is not performed on every tick.
    source.write_bytes(export_data.replace(b"12:00:00Z", b"12:01:00Z"))
    engine.notify_changed({str(source)})
    engine.tick()
    clock[0] += 0.3
    engine.tick()
    assert len(sent) == 2
    assert "Last sync:" in messages[-1]
    store.close()


def test_incomplete_file_then_recovery(tmp_path, export_data, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: clock[0])
    source, store, engine, messages = make_engine(
        tmp_path, b"GuildSyncDB = {", lambda *args: UploadResult(True, "OK")
    )
    engine.tick()
    clock[0] += 1
    engine.tick()
    assert "Incomplete export" in messages[-1] or "Expected" in messages[-1]
    assert store.due(URL) is None
    source.write_bytes(export_data)
    engine.tick()
    clock[0] += 1
    engine.tick()
    assert store.status(URL)[2] is not None
    assert not engine.errors
    store.close()


def test_auth_failure_pauses_until_explicit_retry(tmp_path, export_data):
    calls = []

    def sender(*args):
        calls.append(args)
        return UploadResult(False, "Unauthorized", auth_error=True)

    _, store, engine, _ = make_engine(tmp_path, export_data, sender)
    content_hash, payload = read_export(export_data)[0]
    store.enqueue(URL, content_hash, payload)
    engine.tick()
    assert engine.auth_paused
    store.retry(URL)
    engine.tick()
    assert len(calls) == 1
    engine.auth_paused = False
    engine.tick()
    assert len(calls) == 2
    store.close()


def test_network_backoff_and_no_password_in_logs(tmp_path, export_data, caplog):
    _, store, engine, _ = make_engine(
        tmp_path, export_data, lambda *args: UploadResult(False, "Network unavailable")
    )
    content_hash, payload = read_export(export_data)[0]
    store.enqueue(URL, content_hash, payload)
    engine.tick()
    assert store.due(URL) is None
    row = store.db.execute("SELECT attempts, next_attempt, state FROM uploads").fetchone()
    assert row[0] == 1 and row[2] == "pending"
    assert "test-password" not in caplog.text
    store.close()


def test_missing_file_is_visible(tmp_path):
    _, store, engine, messages = make_engine(tmp_path, b"", lambda *args: UploadResult(True, "OK"))
    settings = replace(engine.settings, sources=[str(tmp_path / "missing.lua")])
    engine = Engine(settings, engine.secret, store, messages.append)
    engine.tick()
    assert "unavailable or locked" in messages[-1]
    store.close()


def test_idle_ticks_do_not_stat_or_read_source_files(tmp_path, export_data, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: clock[0])
    _, store, engine, _ = make_engine(tmp_path, export_data, lambda *args: UploadResult(True, "OK"))
    engine.tick()
    clock[0] += 0.3
    engine.tick()
    assert not engine.pending
    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", lambda *args, **kwargs: pytest.fail("Idle source stat"))
        patch.setattr(Path, "open", lambda *args, **kwargs: pytest.fail("Idle source read"))
        engine.tick()
    store.close()


def test_safety_scan_recovers_a_missed_event(tmp_path, export_data, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: clock[0])
    calls = []

    def sender(*args):
        calls.append(args)
        return UploadResult(True, "OK")

    source, store, engine, _ = make_engine(tmp_path, export_data, sender)
    engine.tick()
    clock[0] += 0.3
    engine.tick()
    source.write_bytes(export_data.replace(b"12:00:00Z", b"12:02:00Z"))
    engine.tick()
    assert len(calls) == 1
    clock[0] += 1
    engine.tick()
    clock[0] += 0.3
    engine.tick()
    assert len(calls) == 2
    store.close()


def test_events_reset_stability_even_when_file_metadata_is_unchanged(
    tmp_path, export_data, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: clock[0])
    calls = []

    def sender(*args):
        calls.append(args)
        return UploadResult(True, "OK")

    source, store, engine, messages = make_engine(tmp_path, export_data, sender)
    engine = Engine(
        replace(engine.settings, stable_seconds=Settings().stable_seconds),
        engine.secret,
        store,
        messages.append,
        sender,
    )
    engine.tick()
    clock[0] += 2.1
    engine.tick()
    engine.next_rescan = 1000
    stat = source.stat()
    source.write_bytes(export_data.replace(b"12:00:00Z", b"12:03:00Z"))
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    engine.notify_changed({str(source)})
    engine.tick()
    clock[0] += 1.5
    engine.notify_changed({str(source)})
    engine.tick()
    clock[0] += 1.5
    engine.tick()
    assert len(calls) == 1
    clock[0] += 0.6
    engine.tick()
    assert len(calls) == 2
    store.close()


def test_queue_retries_without_another_file_event(tmp_path, export_data):
    calls = []

    def sender(*args):
        calls.append(args)
        return UploadResult(len(calls) > 1, "test response")

    _, store, engine, _ = make_engine(tmp_path, export_data, sender)
    store.enqueue(URL, *read_export(export_data)[0])
    engine.tick()
    assert len(calls) == 1
    engine.pending.clear()
    store.retry(URL)
    engine.tick()
    assert len(calls) == 2
    assert store.status(URL)[2] is not None
    store.close()


def test_paused_engine_does_not_busy_wait_after_safety_deadline(tmp_path, monkeypatch):
    store = Store(tmp_path / "queue.sqlite3")
    engine = Engine(Settings(), "", store, lambda text: None)
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: engine.next_rescan + 1)
    assert engine.wait_seconds() == engine.settings.poll_seconds
    store.close()


def test_startup_reads_after_stability_without_waiting_for_safety_interval(
    tmp_path, export_data, monkeypatch
):
    clock = [1.0]
    monkeypatch.setattr("gaddhub_agent.sync.time.monotonic", lambda: clock[0])
    _, store, engine, messages = make_engine(
        tmp_path, export_data, lambda *args: UploadResult(True, "OK")
    )
    engine = Engine(
        replace(engine.settings, rescan_seconds=3600),
        engine.secret,
        store,
        messages.append,
        lambda *args: UploadResult(True, "OK"),
    )
    engine.tick()
    clock[0] += 0.3
    engine.tick()
    assert store.status(URL)[2] is not None
    store.close()


@pytest.mark.parametrize(
    ("result", "outcome", "action"),
    [
        (UploadResult(True, "HTTP 201: snapshot accepted."), "Success:", "HTTP 201"),
        (UploadResult(False, "Connection failed."), "Fail:", "Next retry in"),
        (UploadResult(False, "HTTP 429", retry_after=120), "Fail:", "Next retry in 12"),
        (UploadResult(False, "HTTP 401", auth_error=True), "Fail:", "Uploads paused"),
        (UploadResult(False, "HTTP 422", permanent=True), "Fail:", "Rejected; fix the cause"),
    ],
)
def test_upload_activity_names_file_and_reports_actual_result(
    tmp_path, export_data, caplog, result, outcome, action
):
    caplog.set_level(logging.INFO, logger="gaddhub_agent")

    def sender(*args):
        assert "Attempting to send snapshot from file" in caplog.text
        assert "Success:" not in caplog.text
        return result

    source, store, engine, _ = make_engine(tmp_path, export_data, sender)
    content_hash, payload = read_export(export_data)[0]
    store.enqueue(URL, content_hash, payload, source.name)
    # Exercise retry after a restart, before the new engine has read its source files.
    store.close()
    store = Store(tmp_path / "queue.sqlite3")
    engine.store = store
    engine.tick()
    assert f'file "{source.name}"' in caplog.text
    assert URL in caplog.text
    assert outcome in caplog.text and action in caplog.text
    assert "test-password" not in caplog.text
    assert payload.decode("utf-8") not in caplog.text
    if result.success:
        assert store.due(URL) is None
        assert store.status(URL)[2] is not None
    else:
        assert "Success:" not in caplog.text
    store.close()


def test_legacy_queue_logs_unknown_filename_explicitly(tmp_path, export_data, caplog):
    caplog.set_level(logging.INFO, logger="gaddhub_agent")
    _, store, engine, _ = make_engine(tmp_path, export_data, lambda *args: UploadResult(True, "OK"))
    store.enqueue(URL, *read_export(export_data)[0])
    engine.tick()
    assert "source filename unavailable" in caplog.text
    store.close()


def test_source_filename_cannot_inject_an_extra_log_line(tmp_path, export_data, caplog):
    caplog.set_level(logging.INFO, logger="gaddhub_agent")
    _, store, engine, _ = make_engine(tmp_path, export_data, lambda *args: UploadResult(True, "OK"))
    store.enqueue(URL, *read_export(export_data)[0], source_name="GuildSync.lua\nInjected line")
    engine.tick()
    assert 'file "GuildSync.lua\\nInjected line"' in caplog.text
    assert "\nInjected line" not in caplog.text
    store.close()


def test_missing_configuration_logs_once_without_spamming(tmp_path, caplog):
    store = Store(tmp_path / "queue.sqlite3")
    engine = Engine(Settings(), "", store, lambda text: None)
    engine.tick()
    engine.tick()
    assert caplog.text.count("Sync paused:") == 1
    assert "SavedVariables files" in caplog.text
    assert "password" in caplog.text
    store.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("120", 120),
        ("-1", 0),
        ("garbage", 0),
        ("99999999", 86400),
        ("nan", 0),
    ],
)
def test_retry_after(value, expected):
    assert retry_after(value) == expected
