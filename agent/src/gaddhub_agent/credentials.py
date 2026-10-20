import json
from pathlib import Path


class CredentialsError(ValueError):
    pass


class Credentials:
    """Plaintext, endpoint-scoped passwords in the local application directory."""

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def validate_password(password: str) -> None:
        if not password or any(ord(char) < 33 or ord(char) > 126 for char in password):
            raise CredentialsError("Use a non-empty password with printable ASCII and no spaces.")

    def load(self) -> dict[str, str]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except UnicodeError as exc:
            raise CredentialsError("Cannot read credentials.json: expected UTF-8.") from exc
        try:
            passwords = json.loads(content)
        except ValueError as exc:
            raise CredentialsError("Cannot read credentials.json: invalid password file.") from exc
        if not isinstance(passwords, dict):
            raise CredentialsError(
                "Cannot read credentials.json: expected endpoint/password pairs."
            )
        for endpoint, password in passwords.items():
            if not isinstance(endpoint, str) or not isinstance(password, str):
                raise CredentialsError(
                    "Cannot read credentials.json: invalid endpoint/password pair."
                )
            self.validate_password(password)
        return passwords

    def get(self, endpoint: str) -> str:
        return self.load().get(endpoint, "")

    def set(self, endpoint: str, password: str) -> None:
        self.validate_password(password)
        passwords = self.load()
        passwords[endpoint] = password
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(passwords, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
