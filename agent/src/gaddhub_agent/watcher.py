import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

log = logging.getLogger(__name__)


def path_key(path: str | bytes) -> str:
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


class SourceWatcher(FileSystemEventHandler):
    def __init__(self, wake: Callable[[], None]):
        self.wake = wake
        self.lock = threading.Lock()
        self.sources: dict[str, str] = {}
        self.changed: set[str] = set()
        self.refresh_requested = True
        self.next_refresh = 0.0
        self.observer: BaseObserver | None = None
        self.directories: set[str] = set()

    def configure(self, sources: list[str]) -> None:
        with self.lock:
            self.sources = {path_key(source): source for source in sources}
            self.changed.clear()
            self.refresh_requested = True

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type not in ("created", "modified", "deleted", "moved", "closed"):
            return
        if event.is_directory and event.event_type not in ("created", "deleted", "moved"):
            return
        paths = [path_key(event.src_path)]
        if event.event_type == "moved":
            paths.append(path_key(event.dest_path))
        with self.lock:
            affected = {
                source
                for key, source in self.sources.items()
                if any(
                    key == path or (event.is_directory and key.startswith(path + os.sep))
                    for path in paths
                )
            }
            self.changed.update(affected)
            if affected and event.is_directory:
                self.refresh_requested = True
        if affected:
            self.wake()

    def take_changes(self) -> set[str]:
        with self.lock:
            changed = self.changed.copy()
            self.changed.clear()
        return changed

    def refresh(self, interval: float) -> None:
        now = time.monotonic()
        healthy = self.observer is None or (
            self.observer.is_alive()
            and all(emitter.is_alive() for emitter in self.observer.emitters)
        )
        with self.lock:
            if now < self.next_refresh and not self.refresh_requested and healthy:
                return
            self.refresh_requested = False
            sources = list(self.sources.values())
        self.next_refresh = now + interval
        directories: set[str] = set()
        for source in sources:
            directory = Path(source).parent
            # Watch the closest existing ancestor until a missing directory is created.
            while not directory.is_dir() and directory != directory.parent:
                directory = directory.parent
            directories.add(str(directory))
        if directories == self.directories and healthy:
            return
        if not healthy:
            log.warning(
                "File watcher stopped unexpectedly; restarting it. Safety scans remain active."
            )
        self.close()
        if not directories:
            return
        observer = Observer()
        self.observer = observer
        try:
            observer.start()
        except (OSError, RuntimeError) as exc:
            log.error(
                "File watcher could not start (%s); using safety scans and retrying later.",
                type(exc).__name__,
            )
            self.close()
            return
        for directory in sorted(directories):
            try:
                observer.schedule(self, directory, recursive=False)
                self.directories.add(directory)
            except (OSError, RuntimeError) as exc:
                log.warning(
                    "File watcher unavailable for directory %s (%s); using safety scans "
                    "and retrying later.",
                    json.dumps(directory, ensure_ascii=False),
                    type(exc).__name__,
                )
        if not self.directories:
            self.close()
            log.warning(
                "No directories could be watched; using safety scans every %.1f seconds "
                "until the watcher can restart.",
                interval,
            )
            return
        log.info(
            "File watcher active: %d configured file(s), %d of %d directories. "
            "Safety scan interval: %.1f seconds.",
            len(sources),
            len(self.directories),
            len(directories),
            interval,
        )

    def close(self) -> None:
        if self.observer is not None:
            self.observer.stop()
            if self.observer.ident is not None:
                self.observer.join()
            self.observer = None
        self.directories.clear()
