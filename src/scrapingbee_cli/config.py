"""API key and base URL configuration."""

from __future__ import annotations

import os
from pathlib import Path

ENV_API_KEY = "SCRAPINGBEE_API_KEY"
BASE_URL = "https://app.scrapingbee.com/api/v1"

# Persistent auth .env path (evaluated once; cwd .env is evaluated at load_dotenv() call time)
DOTENV_HOME = Path.home() / ".config" / "scrapingbee-cli" / ".env"


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    """Parse a single .env line; return (key, value) or None."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1].replace('\\"', '"')
    elif value.startswith("'") and value.endswith("'"):
        value = value[1:-1].replace("\\'", "'")
    return key, value


def load_dotenv() -> None:
    """Load .env from current directory and then ~/.config/scrapingbee-cli/.env.
    Sets variables in os.environ only if not already set (env takes precedence).
    """
    # Evaluate cwd at call time (not import time) so it picks up the actual working directory.
    dotenv_cwd = Path.cwd() / ".env"
    for path in (dotenv_cwd, DOTENV_HOME):
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    parsed = _parse_dotenv_line(line)
                    if parsed:
                        key, value = parsed
                        os.environ.setdefault(key, value)
        except OSError:
            pass


def get_api_key(flag_value: str | None = None) -> str:
    """Return API key from environment (after load_dotenv). Raises ValueError if missing."""
    if flag_value:
        return flag_value
    key = os.environ.get(ENV_API_KEY)
    if not key:
        raise ValueError(
            f"API key not set. Run `scrapingbee auth` or set {ENV_API_KEY} (env or .env)."
        )
    return key


def get_api_key_if_set(flag_value: str | None) -> str | None:
    """Return API key from flag or environment, or None if not set. Does not raise."""
    if flag_value:
        return flag_value
    return os.environ.get(ENV_API_KEY) or None


def auth_config_path() -> Path:
    """Path to the persistent auth .env file (used by auth/logout commands)."""
    return DOTENV_HOME


def save_api_key_to_dotenv(api_key: str) -> Path:
    """Write SCRAPINGBEE_API_KEY to ~/.config/scrapingbee-cli/.env.
    Creates parent dirs. Returns path."""
    path = auth_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    parsed = _parse_dotenv_line(line)
                    if parsed:
                        existing[parsed[0]] = parsed[1]
        except OSError:
            pass
    existing[ENV_API_KEY] = api_key
    with open(path, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f'{k}="{v}"\n')
    os.chmod(path, 0o600)
    return path


def remove_api_key_from_dotenv() -> bool:
    """Remove SCRAPINGBEE_API_KEY from ~/.config/scrapingbee-cli/.env.
    Returns True if file was modified."""
    path = auth_config_path()
    if not path.exists():
        return False
    lines: list[str] = []
    removed = False
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parsed = _parse_dotenv_line(line)
                if parsed and parsed[0] == ENV_API_KEY:
                    removed = True
                    continue
                lines.append(line.rstrip("\n"))
        if not removed:
            return False
        if not lines:
            path.unlink()
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        return True
    except OSError:
        return False
