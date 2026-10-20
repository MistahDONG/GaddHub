import json
import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from . import __version__
from .config import Settings, validate_url
from .export import MAX_FILE_BYTES, ExportError, read_export
from .store import Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadResult:
    success: bool
    message: str
    permanent: bool = False
    auth_error: bool = False
    retry_after: float = 0


def upload(url: str, secret: str, content_hash: str, payload: bytes) -> UploadResult:
    validate_url(url)
    try:
        # No ambient .netrc credentials/proxies, no redirects and no response body ingestion.
        with requests.Session() as session:
            session.trust_env = False
            with session.post(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": content_hash,
                    "User-Agent": f"GaddHub-Agent/{__version__}",
                },
                timeout=(5, 20),
                allow_redirects=False,
                stream=True,
            ) as response:
                code = response.status_code
                if code in (200, 201, 204):
                    return UploadResult(True, f"HTTP {code}: snapshot accepted.")
                if code in (401, 403):
                    return UploadResult(
                        False, f"HTTP {code}: check password/access.", auth_error=True
                    )
                if code in (408, 425, 429) or 500 <= code <= 599:
                    delay = retry_after(response.headers.get("Retry-After", ""))
                    return UploadResult(False, f"HTTP {code}: waiting to retry.", retry_after=delay)
                return UploadResult(False, f"HTTP {code}: upload rejected.", permanent=True)
    except requests.exceptions.SSLError:
        return UploadResult(False, "TLS certificate validation failed; check server certificate.")
    except requests.exceptions.Timeout:
        return UploadResult(False, "Network timeout: server did not respond within the time limit.")
    except requests.exceptions.ConnectionError:
        return UploadResult(
            False,
            "Connection failed: DNS lookup, connection refused or server/network unavailable.",
        )
    except requests.exceptions.RequestException:
        return UploadResult(False, "Network error: unable to reach HTTPS endpoint.")


def retry_after(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            seconds = (date - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0
    return min(86400, max(0, seconds)) if not math.isnan(seconds) else 0


@dataclass
class Observed:
    signature: tuple[int, int]
    changed: float
    read_at: float | None = None


class Engine:
    def __init__(
        self,
        settings: Settings,
        secret: str,
        store: Store,
        report: Callable[[str], None],
        sender: Callable[[str, str, str, bytes], UploadResult] = upload,
    ):
        self.settings = settings
        self.secret = secret
        self.store = store
        self.report = report
        self.sender = sender
        self.observed: dict[str, Observed] = {}
        self.auth_paused = False
        self.errors: dict[str, str] = {}
        self.upload_status = ""
        self.configuration_message = ""
        self.active_logged = False
        self.pending = set(settings.sources)
        self.next_rescan = time.monotonic() + settings.rescan_seconds

    def notify_changed(self, sources: set[str]) -> None:
        for source in sources.intersection(self.settings.sources):
            self.pending.add(source)
            self.observed.pop(source, None)

    def wait_seconds(self) -> float:
        if not self.settings.server_url or not self.settings.sources or not self.secret:
            return self.settings.poll_seconds
        now = time.monotonic()
        delay = min(self.settings.poll_seconds, max(0.01, self.next_rescan - now))
        for source in self.pending:
            observed = self.observed.get(source)
            if observed is not None:
                stable_in = observed.changed + self.settings.stable_seconds - now
                if stable_in > 0:
                    delay = min(delay, stable_in)
        return max(0.01, delay)

    def report_error(self, path: str, message: str) -> None:
        if self.errors.get(path) != message:
            log.warning("Fail: %s", message)
        self.errors[path] = message

    def scan(self) -> None:
        now = time.monotonic()
        if now >= self.next_rescan:
            self.pending.update(self.settings.sources)
            self.next_rescan = now + self.settings.rescan_seconds
            log.info("Safety scan: rechecking configured export files.")
        for source in self.settings.sources:
            if source not in self.pending:
                continue
            path = Path(source)
            filename = json.dumps(path.name, ensure_ascii=False)
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                observed = self.observed.get(source)
                if observed is None or observed.signature != signature:
                    self.observed[source] = Observed(signature, now)
                    log.info(
                        "Detected file %s; waiting %.1f seconds for a stable write.",
                        filename,
                        self.settings.stable_seconds,
                    )
                    continue
                if now - observed.changed < self.settings.stable_seconds:
                    continue
                if (
                    observed.read_at is not None
                    and now - observed.read_at < self.settings.rescan_seconds
                ):
                    continue
                observed.read_at = now
                log.info("Reading and validating file %s.", filename)
                with path.open("rb") as file:
                    data = file.read(MAX_FILE_BYTES + 1)
                after = path.stat()
                if (after.st_mtime_ns, after.st_size) != signature:
                    self.observed[source] = Observed(
                        (after.st_mtime_ns, after.st_size), time.monotonic()
                    )
                    log.info("File %s changed while reading; waiting for a stable write.", filename)
                    continue
                snapshots = read_export(data)
                queued = 0
                for content_hash, payload in snapshots:
                    queued += self.store.enqueue(
                        self.settings.server_url, content_hash, payload, path.name
                    )
                log.info(
                    "Validated file %s: %d snapshot(s) queued, %d duplicate(s) skipped.",
                    filename,
                    queued,
                    len(snapshots) - queued,
                )
                self.errors.pop(source, None)
                self.pending.discard(source)
            except (OSError, ExportError, ValueError) as exc:
                if isinstance(exc, OSError):
                    message = f"File {filename}: file unavailable or locked (OS error {exc.errno})."
                else:
                    message = f"File {filename}: {exc}"
                self.report_error(source, message)

    def tick(self) -> None:
        if not self.settings.server_url or not self.settings.sources or not self.secret:
            missing = []
            if not self.settings.server_url:
                missing.append("HTTPS endpoint")
            if not self.settings.sources:
                missing.append("SavedVariables files")
            if not self.secret:
                missing.append("password")
            message = "Sync paused: configure " + ", ".join(missing) + "."
            if message != self.configuration_message:
                log.warning("%s", message)
                self.configuration_message = message
            self.report(message)
            return
        self.configuration_message = ""
        if not self.active_logged:
            log.info(
                "Sync active: watching %d file(s), server %s.",
                len(self.settings.sources),
                self.settings.server_url,
            )
            self.active_logged = True
        self.scan()
        due = self.store.due(self.settings.server_url)
        if due and not self.auth_paused:
            content_hash, payload, attempts = due
            name = self.store.source_name(self.settings.server_url, content_hash)
            origin = (
                f"file {json.dumps(name, ensure_ascii=False)}"
                if name
                else "queued snapshot (source filename unavailable)"
            )
            log.info(
                "Attempting to send snapshot from %s to server %s (attempt %d).",
                origin,
                self.settings.server_url,
                attempts + 1,
            )
            result = self.sender(self.settings.server_url, self.secret, content_hash, payload)
            self.upload_status = result.message
            if result.success:
                self.store.acknowledge(self.settings.server_url, content_hash)
                log.info(
                    "Success: snapshot from %s sent to server %s. %s",
                    origin,
                    self.settings.server_url,
                    result.message,
                )
            else:
                self.auth_paused = result.auth_error
                delay = max(result.retry_after, min(3600, 2 ** min(attempts + 1, 12)))
                wait = delay + random.uniform(0, min(5, delay / 4))
                self.store.fail(
                    self.settings.server_url,
                    content_hash,
                    attempts + 1,
                    wait,
                    result.message,
                    result.permanent,
                )
                if result.auth_error:
                    action = "Uploads paused; check password/access and save or click Retry now."
                elif result.permanent:
                    action = "Rejected; fix the cause and click Retry now."
                else:
                    action = f"Next retry in {wait:.1f} seconds."
                log.warning(
                    "Fail: snapshot from %s to server %s. %s %s",
                    origin,
                    self.settings.server_url,
                    result.message,
                    action,
                )
        pending, rejected, last = self.store.status(self.settings.server_url)
        last_text = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "never"
        state = "AUTH PAUSED. " if self.auth_paused else ""
        messages = list(self.errors.values())
        if self.upload_status:
            messages.append(self.upload_status)
        self.report(
            f"{state}Queued: {pending} | Rejected: {rejected} | Last sync: {last_text}\n"
            + "\n".join(messages)
        )
