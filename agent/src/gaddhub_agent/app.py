from __future__ import annotations

import argparse
import logging
import queue
import sqlite3
import sys
import threading
import tkinter as tk
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from . import __version__
from .config import DEFAULT_SERVER_URL, Settings, validate_url
from .credentials import Credentials, CredentialsError
from .export import ExportError, read_export
from .platform import data_directory, lock_instance, set_autostart
from .store import Store
from .sync import Engine
from .watcher import SourceWatcher

if TYPE_CHECKING:
    from pystray._base import Icon as TrayIcon

log = logging.getLogger(__name__)
MAX_ACTIVITY_LINES = 500


class ActivityLogHandler(logging.Handler):
    def __init__(self, events: queue.Queue[tuple[str, str]]):
        super().__init__(logging.INFO)
        self.events = events
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.events.put(("log", self.format(record)))


def tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 14, 50, 50), fill="#20bfa9")
    draw.polygon([(44, 32), (61, 15), (61, 49)], fill="#20bfa9")
    draw.ellipse((15, 23, 21, 29), fill="#12202a")
    return image


class Application:
    def __init__(self, root: tk.Tk, directory: Path, settings: Settings):
        self.root = root
        self.directory = directory
        self.settings = settings
        self.credentials = Credentials(directory / "credentials.json")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.commands: queue.Queue[tuple[Settings, str]] = queue.Queue()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.worker: threading.Thread | None = None
        self.tray: TrayIcon | None = None
        self.tray_thread: threading.Thread | None = None
        self.tray_stopped = False
        self.closing = False
        root.title(f"GaddHub - Sync agent {__version__}")
        root.geometry(f"820x{min(780, root.winfo_screenheight() - 100)}")
        root.minsize(740, 650)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="GaddHub sync agent", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="HTTPS upload endpoint (including API path)").pack(
            anchor="w", pady=(14, 2)
        )
        self.url = tk.StringVar(value=settings.server_url or DEFAULT_SERVER_URL)
        ttk.Entry(frame, textvariable=self.url).pack(fill="x")
        ttk.Label(
            frame, text="The prefilled .invalid URL is an example, not a running server."
        ).pack(anchor="w")
        ttk.Label(frame, text="Password (stored locally in plaintext in credentials.json)").pack(
            anchor="w", pady=(10, 2)
        )
        self.password = tk.StringVar()
        ttk.Entry(frame, textvariable=self.password, show="*").pack(fill="x")
        ttk.Label(
            frame, text="Leave blank to keep the password saved for this exact endpoint."
        ).pack(anchor="w")
        ttk.Label(frame, text="Configured addon SavedVariables files").pack(
            anchor="w", pady=(10, 2)
        )
        self.sources = tk.Listbox(frame, height=4, selectmode=tk.EXTENDED)
        self.sources.pack(fill="x")
        for source in settings.sources:
            self.sources.insert(tk.END, source)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="Add file...", command=self.add_files).pack(side="left")
        ttk.Button(buttons, text="Remove selected", command=self.remove_files).pack(
            side="left", padx=6
        )
        self.autostart = tk.BooleanVar(value=settings.autostart)
        ttk.Checkbutton(
            frame, text="Start automatically when I sign in", variable=self.autostart
        ).pack(anchor="w", pady=4)
        self.status = tk.StringVar(value="Starting...")
        self.notice = tk.StringVar(
            value=(
                "Linux: the window minimizes instead of hiding, so it remains accessible "
                "even when the desktop has no tray support."
                if sys.platform == "linux"
                else ""
            )
        )
        ttk.Label(frame, textvariable=self.notice, wraplength=680).pack(fill="x", pady=4)
        ttk.Label(frame, textvariable=self.status, wraplength=680).pack(
            fill="x", anchor="w", pady=8
        )
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="Save and sync", command=self.save).pack(side="left")
        ttk.Button(actions, text="Retry now", command=self.retry).pack(side="left", padx=6)
        ttk.Button(actions, text="Hide to tray", command=self.hide).pack(side="left")
        ttk.Button(actions, text="Exit", command=self.close).pack(side="right")
        log_heading = ttk.Frame(frame)
        log_heading.pack(fill="x", pady=(12, 4))
        ttk.Label(log_heading, text=f"Activity log (latest {MAX_ACTIVITY_LINES} lines)").pack(
            side="left"
        )
        ttk.Button(log_heading, text="Clear log", command=self.clear_activity).pack(side="right")
        self.activity = ScrolledText(
            frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        self.activity.pack(fill="both", expand=True)
        self.activity_handler = ActivityLogHandler(self.events)
        package_logger = logging.getLogger("gaddhub_agent")
        package_logger.setLevel(logging.DEBUG)
        package_logger.addHandler(self.activity_handler)
        log.info(
            "GaddHub Agent %s ready. Configure the server and select addon export files to start syncing.",
            __version__,
        )
        root.after(100, self.drain_events)

    def append_activity(self, text: str) -> None:
        self.activity.configure(state=tk.NORMAL)
        self.activity.insert(tk.END, text + "\n")
        lines = int(self.activity.index("end-1c").split(".")[0]) - 1
        if lines > MAX_ACTIVITY_LINES:
            self.activity.delete("1.0", f"{lines - MAX_ACTIVITY_LINES + 1}.0")
        self.activity.see(tk.END)
        self.activity.configure(state=tk.DISABLED)

    def clear_activity(self) -> None:
        self.activity.configure(state=tk.NORMAL)
        self.activity.delete("1.0", tk.END)
        self.activity.configure(state=tk.DISABLED)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.root,
            title="Select addon SavedVariables files",
            filetypes=[("Lua SavedVariables", "*.lua")],
        )
        existing = set(self.sources.get(0, tk.END))
        for path in paths:
            normalized = str(Path(path))
            if normalized not in existing:
                self.sources.insert(tk.END, normalized)
                existing.add(normalized)

    def remove_files(self) -> None:
        for index in reversed(self.sources.curselection()):
            self.sources.delete(index)

    def get_secret(self, url: str) -> str:
        return self.credentials.get(url) if url else ""

    def save(self) -> None:
        try:
            url = validate_url(self.url.get().strip())
            settings = replace(
                self.settings,
                server_url=url,
                sources=list(self.sources.get(0, tk.END)),
                autostart=self.autostart.get(),
            )
            settings.validate()
            if not settings.sources:
                raise ValueError("Select at least one addon SavedVariables file.")
            password = self.password.get()
            if password:
                self.credentials.set(url, password)
            secret = self.get_secret(url)
            if not secret:
                raise ValueError("Enter the shared backend password.")
            set_autostart(settings.autostart)
            settings.save(self.directory / "settings.json")
        except (ValueError, OSError) as exc:
            # Do not show third-party exception text, which may include credentials.
            text = (
                str(exc)
                if isinstance(exc, ValueError)
                else ("Unable to save credentials, autostart or settings. Check file permissions.")
            )
            log.warning("Settings not saved: %s", text)
            messagebox.showerror("Settings not saved", text, parent=self.root)
            return
        self.password.set("")
        self.settings = settings
        for handler in logging.getLogger("gaddhub_agent").handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.setLevel(settings.log_level)
        self.commands.put((settings, secret))
        self.wake.set()
        self.status.set("Settings saved. Checking files...")
        log.info("Settings saved. Checking configured files.")

    def retry(self) -> None:
        try:
            secret = self.get_secret(self.settings.server_url)
        except (OSError, CredentialsError):
            log.error("Cannot read the local credentials.json file; retry cancelled.")
            messagebox.showerror(
                "Password file error",
                "Cannot read the local credentials.json file.",
                parent=self.root,
            )
            return
        self.commands.put((self.settings, secret))
        self.wake.set()
        log.info("Retry requested. Rechecking files and retrying queued/rejected snapshots.")

    def start(self, background: bool) -> None:
        try:
            secret = self.get_secret(self.settings.server_url)
        except (OSError, CredentialsError):
            secret = ""
            self.events.put(("error", "Cannot read local credentials.json. Sync is paused."))
        self.worker = threading.Thread(target=self.run_worker, args=(secret,), daemon=False)
        self.worker.start()
        try:
            self.start_tray()
        except (ImportError, OSError, RuntimeError, ValueError):
            log.warning("Tray integration unavailable; using the settings window.")
            self.notice.set("Tray unavailable. Use the taskbar/window list to reopen this window.")
            if self.tray is not None:
                self.tray.stop()
                self.tray = None
        if background:
            if self.tray is not None and sys.platform == "win32":
                self.root.withdraw()
            else:
                self.show()
                self.root.iconify()

    def start_tray(self) -> None:
        import pystray

        tray = pystray.Icon(
            "GaddHub",
            tray_image(),
            "GaddHub sync",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Open GaddHub", lambda: self.events.put(("show", "")), default=True
                ),
                pystray.MenuItem("Exit", lambda: self.events.put(("exit", ""))),
            ),
        )
        self.tray = tray
        if sys.platform == "linux":
            # GTK needs its own event loop; tkinter does not drive GLib.
            self.tray_thread = threading.Thread(target=self.run_tray, daemon=True)
            self.tray_thread.start()
        else:
            tray.run_detached()

    def run_tray(self) -> None:
        if self.tray is None:
            return
        try:
            self.tray.run()
        except (OSError, RuntimeError, ValueError):
            log.warning("Tray event loop stopped; using the settings window.")
            self.events.put(("tray_error", "Tray stopped. Use the window list to open settings."))

    def run_worker(self, secret: str) -> None:
        store: Store | None = None
        watcher = SourceWatcher(self.wake.set)
        try:
            store = Store(self.directory / "sync.sqlite3")
            engine = Engine(
                self.settings, secret, store, lambda text: self.events.put(("status", text))
            )
            watcher.configure(self.settings.sources)
            while not self.stop.is_set():
                self.wake.clear()
                while True:
                    try:
                        settings, secret = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    store.retry(settings.server_url)
                    engine = Engine(
                        settings, secret, store, lambda text: self.events.put(("status", text))
                    )
                    watcher.configure(settings.sources)
                watcher.refresh(engine.settings.rescan_seconds)
                engine.notify_changed(watcher.take_changes())
                engine.tick()
                self.wake.wait(engine.wait_seconds())
        except (OSError, sqlite3.Error, ValueError):
            log.error("Sync worker stopped due to a local storage or configuration error.")
            self.events.put(
                (
                    "error",
                    (
                        "Sync stopped: local storage/configuration error. Check disk space, "
                        "permissions and settings, then restart the agent."
                    ),
                )
            )
        finally:
            watcher.close()
            if store is not None:
                store.close()

    def drain_events(self) -> None:
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "show":
                    self.show()
                elif kind == "log":
                    self.append_activity(text)
                elif kind == "exit":
                    self.close()
                elif kind == "tray_error":
                    self.notice.set(text)
                    self.show()
                elif kind == "error":
                    self.status.set(text)
                    self.show()
                    messagebox.showerror("GaddHub", text, parent=self.root)
                else:
                    self.status.set(text)
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self.drain_events)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        if sys.platform == "win32" and self.tray is not None and self.tray.visible:
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.iconify()

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.stop.set()
        self.wake.set()
        self.status.set("Stopping; waiting for any active HTTPS request...")
        self.wait_for_worker()

    def wait_for_worker(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100, self.wait_for_worker)
            return
        if self.tray is not None and not self.tray_stopped:
            self.tray.stop()
            self.tray_stopped = True
        if self.tray_thread is not None and self.tray_thread.is_alive():
            self.root.after(100, self.wait_for_worker)
            return
        logging.getLogger("gaddhub_agent").removeHandler(self.activity_handler)
        self.activity_handler.close()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="GaddHub Windows/Linux sync agent")
    parser.add_argument("--background", action="store_true", help="Start hidden in the system tray")
    parser.add_argument("--check-export", type=Path, help="Validate an export without uploading")
    args = parser.parse_args()
    if args.check_export:
        try:
            with args.check_export.open("rb") as file:
                snapshots = read_export(file.read(8 * 1024 * 1024 + 1))
        except (OSError, ExportError) as exc:
            parser.exit(1, f"Invalid export: {exc}\n")
        print(f"Valid export: {len(snapshots)} snapshot(s). No upload performed.")
        return
    directory = data_directory()
    root = tk.Tk()
    root.withdraw()
    try:
        lock = lock_instance(directory / "agent.lock")
    except OSError:
        messagebox.showerror(
            "GaddHub",
            "Agent already running or lock unavailable. Check the system tray or window list.",
            parent=root,
        )
        root.destroy()
        return
    try:
        try:
            settings = Settings.load(directory / "settings.json")
        except (OSError, ValueError, TypeError):
            messagebox.showerror(
                "GaddHub",
                "Cannot read settings.json. Correct or remove the file and restart.",
                parent=root,
            )
            root.destroy()
            return
        handler = RotatingFileHandler(
            directory / "agent.log", maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        handler.setLevel(settings.log_level)
        # Only our own sanitized messages go to disk, never HTTP debug output.
        logging.getLogger("gaddhub_agent").setLevel(logging.DEBUG)
        logging.getLogger("gaddhub_agent").addHandler(handler)
        application = Application(root, directory, settings)
        application.start(args.background)
        if not args.background:
            application.show()
        root.mainloop()
    finally:
        lock.close()
