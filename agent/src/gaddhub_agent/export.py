"""Read a restricted Lua data grammar; never evaluate Lua code."""

import hashlib
import json
import re
from functools import lru_cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOTS = 100
MAX_DEPTH = 32
MAX_NODES = 200_000
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
FIELD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\s*=")
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


class ExportError(ValueError):
    pass


class LuaReader:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.nodes = 0

    def skip(self) -> None:
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text.startswith("--", self.pos):
                end = self.text.find("\n", self.pos)
                self.pos = len(self.text) if end == -1 else end + 1
            else:
                break

    def take(self, token: str) -> bool:
        self.skip()
        if self.text.startswith(token, self.pos):
            self.pos += len(token)
            return True
        return False

    def expect(self, token: str) -> None:
        if not self.take(token):
            raise ExportError(f"Expected {token!r} at position {self.pos}.")

    def identifier(self) -> str:
        self.skip()
        match = IDENTIFIER.match(self.text, self.pos)
        if not match:
            raise ExportError(f"Expected a field name at position {self.pos}.")
        self.pos += len(match[0])
        return match[0]

    def string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        chars: list[str] = []
        escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'"}
        while self.pos < len(self.text):
            char = self.text[self.pos]
            self.pos += 1
            if char == quote:
                return "".join(chars)
            if char == "\\":
                if self.pos >= len(self.text):
                    break
                char = self.text[self.pos]
                self.pos += 1
                if char.isascii() and char.isdigit():
                    digits = char
                    while len(digits) < 3 and self.pos < len(self.text):
                        next_char = self.text[self.pos]
                        if not (next_char.isascii() and next_char.isdigit()):
                            break
                        digits += next_char
                        self.pos += 1
                    value = int(digits)
                    if value > 255:
                        raise ExportError("Lua byte escape exceeds 255.")
                    # Decode byte escapes together with UTF-8 literal text below.
                    chars.append(chr(0xDC00 + value))
                elif char in escapes:
                    chars.append(escapes[char])
                else:
                    raise ExportError("Unsupported Lua string escape.")
            elif char in "\r\n" or ord(char) < 32:
                raise ExportError("Unescaped control character in Lua string.")
            else:
                chars.append(char)
        raise ExportError("Unfinished Lua string.")

    def value(self, depth: int = 0) -> Any:
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise ExportError("Lua data exceeds complexity limits.")
        self.skip()
        if self.pos >= len(self.text):
            raise ExportError("Incomplete export.")
        if self.text[self.pos] in "\"'":
            raw = self.string()
            data = bytearray()
            for char in raw:
                if 0xDC00 <= ord(char) <= 0xDCFF:
                    data.append(ord(char) - 0xDC00)
                else:
                    data.extend(char.encode("utf-8"))
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ExportError("String is not valid UTF-8.") from exc
        if self.take("{"):
            values: dict[Any, Any] = {}
            implicit_index = 1
            while not self.take("}"):
                if self.take("["):
                    key = self.value(depth + 1)
                    if type(key) not in (str, int):
                        raise ExportError("Table keys must be strings or integers.")
                    self.expect("]")
                    self.expect("=")
                else:
                    match = FIELD.match(self.text, self.pos)
                    if match:
                        key = self.identifier()
                        self.expect("=")
                    else:
                        key = implicit_index
                        implicit_index += 1
                if key in values:
                    raise ExportError("Duplicate Lua table key.")
                values[key] = self.value(depth + 1)
                if not self.take(",") and not self.take(";"):
                    self.expect("}")
                    break
            if values and all(type(key) is int for key in values):
                if set(values) != set(range(1, len(values) + 1)):
                    raise ExportError("Sparse Lua arrays are not supported.")
                return [values[index] for index in range(1, len(values) + 1)]
            if any(not isinstance(key, str) for key in values):
                raise ExportError("Mixed Lua table keys are not supported.")
            return values
        match = NUMBER.match(self.text, self.pos)
        if match:
            self.pos += len(match[0])
            try:
                return json.loads(match[0])
            except ValueError as exc:
                raise ExportError("Invalid number.") from exc
        word = self.identifier()
        if word in ("true", "false", "nil"):
            return {"true": True, "false": False, "nil": None}[word]
        raise ExportError("Executable Lua and unknown values are not allowed.")

    def read(self) -> Any:
        if self.identifier() != "GuildSyncDB":
            raise ExportError("Expected the GuildSyncDB SavedVariable.")
        self.expect("=")
        value = self.value()
        self.take(";")
        self.skip()
        if self.pos != len(self.text):
            raise ExportError("Unexpected content after GuildSyncDB.")
        return value


@lru_cache(maxsize=1)
def validator() -> Draft202012Validator:
    schema = json.loads(
        files("schemas").joinpath("snapshot-v1.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, format_checker=FormatChecker())


def canonical_snapshot(snapshot: Any) -> tuple[str, bytes]:
    error = next(validator().iter_errors(snapshot), None)
    if error is not None:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        # Do not include payload values, which could contain private data.
        raise ExportError(f"Snapshot schema validation failed at {path} ({error.validator}).")
    try:
        payload = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ExportError("Snapshot contains invalid JSON data.") from exc
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ExportError("Snapshot exceeds 2 MiB.")
    return hashlib.sha256(payload).hexdigest(), payload


def read_export(data: bytes) -> list[tuple[str, bytes]]:
    if len(data) > MAX_FILE_BYTES:
        raise ExportError("Export exceeds 8 MiB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExportError("Export must be UTF-8.") from exc
    root = LuaReader(text).read()
    if not isinstance(root, dict) or set(root) != {"schema_version", "snapshots"}:
        raise ExportError("Expected schema_version and snapshots in GuildSyncDB.")
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise ExportError("Unsupported export schema version.")
    snapshots = root["snapshots"]
    if snapshots == {}:
        snapshots = []
    if not isinstance(snapshots, list) or len(snapshots) > MAX_SNAPSHOTS:
        raise ExportError("Expected at most 100 snapshots.")
    result = []
    for snapshot in snapshots:
        if isinstance(snapshot, dict) and isinstance(snapshot.get("sections"), dict):
            for section in snapshot["sections"].values():
                if isinstance(section, dict) and section.get("items") == {}:
                    section["items"] = []
        result.append(canonical_snapshot(snapshot))
    return result
