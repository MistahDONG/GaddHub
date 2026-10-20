import os
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from gaddhub_agent.watcher import SourceWatcher, path_key
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    FileClosedNoWriteEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
)


@pytest.mark.parametrize("event_class", [FileCreatedEvent, FileModifiedEvent, FileDeletedEvent])
def test_file_events_wake_only_for_configured_files(tmp_path, event_class):
    source = str(tmp_path / "GuildSync.lua")
    wake = MagicMock()
    watcher = SourceWatcher(wake)
    watcher.configure([source])
    watcher.on_any_event(event_class(str(tmp_path / "OtherAddon.lua")))
    wake.assert_not_called()
    watcher.on_any_event(event_class(source))
    wake.assert_called_once()
    assert watcher.take_changes() == {source}
    assert watcher.take_changes() == set()


def test_read_events_and_directory_modifications_are_ignored(tmp_path):
    source = str(tmp_path / "GuildSync.lua")
    wake = MagicMock()
    watcher = SourceWatcher(wake)
    watcher.configure([source])
    for event in (
        FileOpenedEvent(source),
        FileClosedNoWriteEvent(source),
        DirModifiedEvent(str(tmp_path)),
    ):
        watcher.on_any_event(event)
    wake.assert_not_called()


def test_atomic_move_checks_both_source_and_destination(tmp_path):
    source = str(tmp_path / "GuildSync.lua")
    watcher = SourceWatcher(lambda: None)
    watcher.configure([source])
    watcher.on_any_event(FileMovedEvent(str(tmp_path / "temporary.tmp"), source))
    assert watcher.take_changes() == {source}
    watcher.on_any_event(FileMovedEvent(source, str(tmp_path / "backup.lua")))
    assert watcher.take_changes() == {source}


def test_configure_removes_stale_sources_and_queued_events(tmp_path):
    old, new = (str(tmp_path / name) for name in ("Old.lua", "New.lua"))
    watcher = SourceWatcher(lambda: None)
    watcher.configure([old])
    watcher.on_any_event(FileModifiedEvent(old))
    watcher.configure([new])
    watcher.on_any_event(FileModifiedEvent(old))
    assert watcher.take_changes() == set()
    watcher.on_any_event(FileModifiedEvent(new))
    assert watcher.take_changes() == {new}


def test_related_directory_creation_requests_watch_refresh(tmp_path):
    parent = tmp_path / "new-directory"
    source = str(parent / "GuildSync.lua")
    watcher = SourceWatcher(lambda: None)
    watcher.configure([source])
    watcher.refresh_requested = False
    watcher.on_any_event(DirCreatedEvent(str(parent)))
    assert watcher.take_changes() == {source}
    assert watcher.refresh_requested


@pytest.mark.skipif(os.name != "nt", reason="Windows path comparison")
def test_windows_event_paths_are_case_insensitive(tmp_path):
    source = str(tmp_path / "GuildSync.lua")
    watcher = SourceWatcher(lambda: None)
    watcher.configure([source])
    watcher.on_any_event(FileModifiedEvent(source.upper()))
    assert watcher.take_changes() == {source}


@pytest.mark.parametrize("operation", ["write", "replace", "recreate"])
def test_native_observer_detects_changes_and_stops_cleanly(tmp_path, operation):
    source = tmp_path / "GuildSync.lua"
    source.write_text("initial", encoding="utf-8")
    wake = threading.Event()
    watcher = SourceWatcher(wake.set)
    watcher.configure([str(source)])
    watcher.refresh(30)
    observer = watcher.observer
    assert observer is not None and observer.is_alive()
    emitters = list(observer.emitters)
    try:
        if operation == "write":
            source.write_text("updated", encoding="utf-8")
        elif operation == "replace":
            temporary = tmp_path / "export.tmp"
            temporary.write_text("updated", encoding="utf-8")
            temporary.replace(source)
        else:
            source.unlink()
            source.write_text("updated", encoding="utf-8")
        assert wake.wait(5), "Native filesystem event was not delivered"
        assert watcher.take_changes() == {str(source)}
    finally:
        watcher.close()
    assert not observer.is_alive()
    assert all(not emitter.is_alive() for emitter in emitters)


def test_native_watch_recovers_when_a_missing_parent_is_created(tmp_path):
    parent = tmp_path / "Account" / "SavedVariables"
    source = str(parent / "GuildSync.lua")
    wake = threading.Event()
    watcher = SourceWatcher(wake.set)
    watcher.configure([source])
    try:
        watcher.refresh(30)
        assert watcher.directories == {str(tmp_path)}
        parent.mkdir(parents=True)
        assert wake.wait(5)
        watcher.take_changes()
        watcher.refresh(30)
        assert watcher.directories == {str(parent)}
        wake.clear()
        Path(source).write_text("export", encoding="utf-8")
        assert wake.wait(5)
        assert watcher.take_changes() == {source}
    finally:
        watcher.close()


def test_registration_failure_is_visible_and_retried(tmp_path, monkeypatch, caplog):
    observer = MagicMock()
    observer.is_alive.return_value = True
    observer.emitters = []
    observer.schedule.side_effect = OSError("do not expose arbitrary exception text")
    monkeypatch.setattr("gaddhub_agent.watcher.Observer", lambda: observer)
    watcher = SourceWatcher(lambda: None)
    watcher.configure([str(tmp_path / "GuildSync.lua")])
    try:
        watcher.refresh(30)
        assert not watcher.directories
        assert "using safety scans" in caplog.text
        assert "do not expose" not in caplog.text
        observer.schedule.side_effect = None
        watcher.configure([str(tmp_path / "GuildSync.lua")])
        watcher.refresh(30)
        assert watcher.directories == {str(tmp_path)}
    finally:
        watcher.close()
    observer.stop.assert_called()


def test_idle_refresh_does_not_poll_directories(tmp_path, monkeypatch):
    source = str(tmp_path / "GuildSync.lua")
    watcher = SourceWatcher(lambda: None)
    watcher.configure([source])
    try:
        watcher.refresh(3600)
        with monkeypatch.context() as patch:
            patch.setattr(Path, "is_dir", lambda *args: pytest.fail("Idle directory poll"))
            watcher.refresh(3600)
            watcher.on_any_event(FileModifiedEvent(source))
            watcher.refresh(3600)
    finally:
        watcher.close()


def test_dead_emitter_is_reported_and_restarted_before_safety_scan(tmp_path, monkeypatch, caplog):
    old_observer = MagicMock()
    old_observer.is_alive.return_value = True
    emitter = MagicMock()
    emitter.is_alive.return_value = False
    old_observer.emitters = [emitter]
    replacement = MagicMock()
    replacement.is_alive.return_value = True
    replacement.emitters = []
    monkeypatch.setattr("gaddhub_agent.watcher.Observer", lambda: replacement)
    watcher = SourceWatcher(lambda: None)
    watcher.configure([str(tmp_path / "GuildSync.lua")])
    watcher.observer = old_observer
    watcher.directories = {str(tmp_path)}
    watcher.refresh_requested = False
    watcher.next_refresh = float("inf")
    try:
        watcher.refresh(30)
        assert "stopped unexpectedly" in caplog.text
        old_observer.stop.assert_called_once()
        assert watcher.observer is replacement
        replacement.schedule.assert_called_once()
    finally:
        watcher.close()


def test_start_failure_keeps_safety_scans_and_allows_retry(tmp_path, monkeypatch, caplog):
    failed = MagicMock()
    failed.ident = None
    failed.start.side_effect = RuntimeError("private exception detail")
    replacement = MagicMock()
    replacement.is_alive.return_value = True
    replacement.emitters = []
    observers = iter([failed, replacement])
    monkeypatch.setattr("gaddhub_agent.watcher.Observer", lambda: next(observers))
    watcher = SourceWatcher(lambda: None)
    source = str(tmp_path / "GuildSync.lua")
    watcher.configure([source])
    try:
        watcher.refresh(30)
        assert watcher.observer is None
        assert "using safety scans" in caplog.text
        assert "private exception" not in caplog.text
        failed.stop.assert_called_once()
        failed.join.assert_not_called()
        watcher.configure([source])
        watcher.refresh(30)
        assert watcher.observer is replacement
    finally:
        watcher.close()


def test_path_normalization_does_not_require_an_existing_file(tmp_path):
    source = tmp_path / "missing" / ".." / "GuildSync.lua"
    assert path_key(str(source)) == path_key(str(tmp_path / "GuildSync.lua"))
