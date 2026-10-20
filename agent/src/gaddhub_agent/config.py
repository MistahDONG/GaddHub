import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_SERVER_URL = "https://gaddhub.example.invalid/v1/sync/snapshots"


def validate_url(url: str) -> str:
    if not isinstance(url, str):
        raise TypeError("Server URL must be a string.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Server URL has an invalid host or port.") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in url)
        or "\\" in url
        or port == 0
    ):
        raise ValueError("Use a complete HTTPS endpoint without credentials, query or fragment.")
    return url


@dataclass
class Settings:
    server_url: str = DEFAULT_SERVER_URL
    sources: list[str] = field(default_factory=list)
    autostart: bool = True
    stable_seconds: float = 2.0
    poll_seconds: float = 2.0
    rescan_seconds: float = 30.0
    log_level: str = "INFO"

    def validate(self) -> None:
        if not isinstance(self.server_url, str):
            raise TypeError("Server URL must be a string.")
        if self.server_url:
            validate_url(self.server_url)
        if not isinstance(self.sources, list) or any(
            not isinstance(path, str)
            or not Path(path).is_absolute()
            or Path(path).suffix.lower() != ".lua"
            for path in self.sources
        ):
            raise ValueError("Sources must be absolute paths to configured .lua files.")
        if type(self.autostart) is not bool:
            raise ValueError("autostart must be true or false.")
        for value in (self.stable_seconds, self.poll_seconds, self.rescan_seconds):
            if type(value) not in (int, float) or not 0.2 <= value <= 3600:
                raise ValueError("Polling and stability intervals must be between 0.2 and 3600 s.")
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError("Invalid logging level.")

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        settings = cls(**json.loads(path.read_text(encoding="utf-8")))
        settings.validate()
        return settings

    def save(self, path: Path) -> None:
        self.validate()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(path)
