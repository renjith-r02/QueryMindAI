"""Read and update KEY=value settings in .env config files, keeping comments and other lines.

Changes are also applied to os.environ, so settings read with os.getenv see them
without a restart.
"""

import os
import re
import tempfile
import threading
from pathlib import Path

from dotenv import dotenv_values

_LOCK = threading.Lock()
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_SAFE = re.compile(r"^[A-Za-z0-9_./:@+,-]*$")

# Variables set in the server's own environment before any .env file was loaded.
# A restart re-applies them over the file, so the admin screens warn about them.
SHELL_ENV_KEYS = frozenset(os.environ)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {key: value or "" for key, value in dotenv_values(path).items()}


def update_env_file(path: Path, changes: dict[str, str | None]) -> None:
    """Set (str) or remove (None) keys in the file and in os.environ."""
    with _LOCK:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        pending = dict(changes)
        output = []
        for line in lines:
            match = _LINE.match(line)
            if match and match.group(1) in changes:
                key = match.group(1)
                if key in pending and pending[key] is not None:
                    output.append(f"{key}={_quote(pending[key])}")
                pending.pop(key, None)  # drop later duplicates of the same key
                continue
            output.append(line)
        additions = [f"{key}={_quote(value)}" for key, value in pending.items() if value is not None]
        if additions:
            if output and output[-1].strip():
                output.append("")
            output += additions

        path.parent.mkdir(parents=True, exist_ok=True)
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600  # new files may hold secrets
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
            tmp.write("\n".join(output) + "\n")
        os.chmod(tmp.name, mode)
        os.replace(tmp.name, path)

        for key, value in changes.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Config values cannot contain line breaks")
    if _SAFE.match(value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def secret_hint(value: str | None) -> str | None:
    """'…abcd' for a configured secret, so admins can recognise it without seeing it."""
    if not value:
        return None
    return "…" + value[-4:] if len(value) >= 12 else "set"
