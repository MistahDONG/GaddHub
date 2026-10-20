import gc
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from gaddhub_agent import app as app_module
from gaddhub_agent.config import DEFAULT_SERVER_URL, Settings
from gaddhub_agent.credentials import Credentials
from gaddhub_agent.sync import Engine, UploadResult
from gaddhub_agent.watcher import SourceWatcher

pytestmark = pytest.mark.skipif(
    os.environ.get("GADDHUB_UI_TEST") != "1", reason="Requires a graphical session or Xvfb"
)


@pytest.fixture
def application(tmp_path, request):
    gc.collect()
    root = tk.Tk()
    root.withdraw()
    application = app_module.Application(root, tmp_path, getattr(request, "param", Settings()))
    closed = []
    root.bind("<Destroy>", lambda event: closed.append(event.widget is root))
    yield application
    application.close()
    deadline = time.monotonic() + 5
    while not any(closed) and time.monotonic() < deadline:
        root.update()
        time.sleep(0.05)
    assert any(closed), "Application did not stop cleanly."


def test_window_saves_local_password_and_preserves_blank_field(
    application, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(app_module, "set_autostart", lambda enabled: None)
    errors = []
    monkeypatch.setattr(
        app_module.messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    app = application
    endpoint = "https://example.invalid/upload"
    app.url.set(endpoint)
    app.sources.insert(tk.END, str(tmp_path / "GuildSync.lua"))
    app.password.set("local-test-password")
    app.save()
    assert not errors
    assert app.password.get() == ""
    assert Credentials(tmp_path / "credentials.json").get(endpoint) == "local-test-password"
    assert app.commands.get_nowait()[1] == "local-test-password"
    app.save()
    assert not errors
    assert app.commands.get_nowait()[1] == "local-test-password"
    assert "local-test-password" not in (tmp_path / "settings.json").read_text()
    app.url.set(endpoint + "/other")
    app.save()
    assert len(errors) == 1
    assert app.commands.empty()
    app.drain_events()
    assert "local-test-password" not in caplog.text
    assert "local-test-password" not in app.activity.get("1.0", "end-1c")


def test_real_tray_window_and_worker(application):
    app = application
    app.start(background=True)
    deadline = time.monotonic() + 5
    while (app.tray is None or not app.tray.visible) and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.05)
    assert app.tray is not None
    assert app.tray.visible
    if sys.platform == "win32":
        assert app.root.state() == "withdrawn"
    else:
        assert app.root.state() != "withdrawn"
    assert app.tray.menu is not None
    app.tray()
    deadline = time.monotonic() + 2
    while app.root.state() != "normal" and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.05)
    assert app.root.state() == "normal"
    assert app.worker is not None and app.worker.is_alive()


def test_tray_import_failure_keeps_window_accessible(application, monkeypatch, caplog):
    def unavailable():
        raise ImportError("Test missing desktop dependency")

    monkeypatch.setattr(application, "start_tray", unavailable)
    application.start(background=True)
    application.root.update()
    assert application.tray is None
    assert application.root.state() != "withdrawn"
    assert "Tray unavailable" in application.notice.get()
    assert "Tray integration unavailable" in caplog.text
    assert application.worker is not None and application.worker.is_alive()


def test_linux_hide_never_withdraws_window(application, monkeypatch):
    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="linux"))
    application.tray = MagicMock(visible=True)
    application.show()
    application.hide()
    application.root.update()
    assert application.root.state() != "withdrawn"


@pytest.mark.parametrize(
    "application",
    [
        Settings(),
        Settings(server_url=""),
        Settings(server_url="https://existing.example.org/upload"),
    ],
    indirect=True,
)
def test_window_prefills_example_url_without_overwriting_existing_url(application, tmp_path):
    assert application.url.get() == (application.settings.server_url or DEFAULT_SERVER_URL)
    assert not (tmp_path / "settings.json").exists()


def test_activity_is_queued_from_worker_and_displayed_on_main_thread(application):
    application.drain_events()
    application.clear_activity()
    logger = logging.getLogger("gaddhub_agent.sync")
    worker = threading.Thread(target=lambda: logger.warning("Fail: server unavailable."))
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert application.activity.get("1.0", "end-1c") == ""
    application.drain_events()
    text = application.activity.get("1.0", "end-1c")
    assert "WARNING Fail: server unavailable." in text
    assert text[2] == ":" and text[5] == ":"
    assert str(application.activity["state"]) == "disabled"


def test_activity_log_is_bounded_and_clearable(application):
    application.drain_events()
    application.clear_activity()
    for index in range(app_module.MAX_ACTIVITY_LINES + 20):
        application.append_activity(f"Activity {index}")
    lines = application.activity.get("1.0", "end-1c").splitlines()
    assert len(lines) == app_module.MAX_ACTIVITY_LINES
    assert lines[0] == "Activity 20"
    assert lines[-1] == f"Activity {app_module.MAX_ACTIVITY_LINES + 19}"
    application.clear_activity()
    assert application.activity.get("1.0", "end-1c") == ""


def test_activity_handler_is_detached_after_close(application):
    logger = logging.getLogger("gaddhub_agent")
    assert application.activity_handler in logger.handlers
    application.close()
    assert application.activity_handler not in logger.handlers


def test_activity_still_shows_attempts_when_disk_log_only_records_errors(application, tmp_path):
    handler = RotatingFileHandler(tmp_path / "errors.log", encoding="utf-8")
    handler.setLevel(logging.ERROR)
    logger = logging.getLogger("gaddhub_agent")
    logger.addHandler(handler)
    try:
        logger.info("Attempting to send snapshot from file GuildSync.lua.")
        application.drain_events()
        assert "Attempting to send" in application.activity.get("1.0", "end-1c")
        assert (tmp_path / "errors.log").read_text() == ""
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_log_is_visible_at_minimum_window_size(application):
    application.show()
    application.root.geometry("740x650")
    application.root.update()
    assert application.activity.winfo_ismapped()
    bottom = application.activity.winfo_rooty() + application.activity.winfo_height()
    assert bottom <= application.root.winfo_rooty() + application.root.winfo_height()
    assert application.activity.winfo_height() >= 60


def test_worker_wakes_on_native_events_and_reconfigures_without_idle_polling(
    application, tmp_path, export_data, monkeypatch
):
    old_directory = tmp_path / "old"
    new_directory = tmp_path / "new"
    old_directory.mkdir()
    new_directory.mkdir()
    old_source = old_directory / "GuildSync.lua"
    new_source = new_directory / "GuildSync.lua"
    old_source.write_bytes(export_data)
    new_source.write_bytes(export_data.replace(b"12:00:00Z", b"12:01:00Z"))
    settings = Settings(
        sources=[str(old_source)], stable_seconds=0.2, poll_seconds=3600, rescan_seconds=3600
    )
    application.settings = settings
    application.credentials.set(settings.server_url, "test-password")
    sent = queue.Queue()
    watchers = []

    def sender(url, secret, content_hash, payload):
        sent.put(payload)
        return UploadResult(True, "OK")

    def create_watcher(wake):
        watcher = SourceWatcher(wake)
        watchers.append(watcher)
        return watcher

    def unavailable_tray():
        raise RuntimeError("No tray needed for this worker test")

    monkeypatch.setattr(app_module, "SourceWatcher", create_watcher)
    monkeypatch.setattr(
        app_module,
        "Engine",
        lambda settings, secret, store, report: Engine(settings, secret, store, report, sender),
    )
    monkeypatch.setattr(application, "start_tray", unavailable_tray)
    application.start(background=False)
    assert b"12:00:00Z" in sent.get(timeout=5)
    old_observer = watchers[0].observer
    assert old_observer is not None
    application.commands.put((replace(settings, sources=[str(new_source)]), "test-password"))
    application.wake.set()
    assert b"12:01:00Z" in sent.get(timeout=5)
    assert not old_observer.is_alive()
    old_source.write_bytes(export_data.replace(b"12:00:00Z", b"12:02:00Z"))
    new_source.write_bytes(export_data.replace(b"12:00:00Z", b"12:03:00Z"))
    assert b"12:03:00Z" in sent.get(timeout=5)
    assert sent.empty()
    observer = watchers[0].observer
    assert observer is not None
    emitters = list(observer.emitters)
    application.close()
    assert application.worker is not None
    application.worker.join(timeout=5)
    assert not application.worker.is_alive()
    assert not observer.is_alive()
    assert all(not emitter.is_alive() for emitter in emitters)
